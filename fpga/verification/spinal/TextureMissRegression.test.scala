package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core.sim._
import voodoo.Config
import voodoo.texture.{Tmu, TmuTextureCache}

/** Cold-cache response values must match the filling beat, including stalls. */
class TextureMissRegression extends AnyFunSuite {
  private val c = Config.voodoo1().copy(
    useTexFillCache = true, packedTexLayout = true,
    texFillCacheSlots = 16, texFillRequestWindow = 16)

  private def setPoint(dut: TmuTextureCache, address: Int): Unit = {
    val req = dut.io.sampleRequest.payload
    req.pointAddr #= address
    req.biAddr0 #= address
    req.biAddr1 #= address
    req.biAddr2 #= address
    req.biAddr3 #= address
    req.lodBase #= 0
    req.lodShift #= 8
    req.is16Bit #= true
    req.bilinear #= false
    req.passthrough.format #= 10 // RGB565
    req.passthrough.bilinear #= false
    req.passthrough.nccTableSelect #= false
    req.passthrough.ds #= 0
    req.passthrough.dt #= 0
    for (lod <- 0 until 9) {
      val size = 1 << (2 * (8 - lod).max(0) + 1)
      val base = (0 until lod).map(i => 1 << (2 * (8 - i).max(0) + 1)).sum
      req.texTables.texBase(lod) #= base
      req.texTables.texEnd(lod) #= base + size
      req.texTables.texShift(lod) #= (8 - lod).max(0)
    }
    // Public packed-layout metadata for 16-bit LOD0, row width256.
    def bank(addr: Int): Int =
      ((((addr >> 8) & 1) | ((addr >> 9) & 1)) << 1) | ((addr & 1) | ((addr >> 1) & 1))
    val lineBase = address & ~(c.texFillLineWords * 4 - 1)
    for (tap <- 0 until 4) {
      req.tapPackedBank(tap) #= bank(address)
      req.tapPackedPair(tap) #= false
      req.tapStartupDecode(tap).valid #= 15
      req.tapStartupDecode(tap).pair #= 0
      for (byte <- 0 until 4)
        req.tapStartupDecode(tap).bank(byte) #= bank(lineBase + byte)
    }
  }

  test("point cold miss returns current fill texel under memory/output stalls and agrees with later hit") {
    SimConfig.withIVerilog.compile(TmuTextureCache(c)).doSim { dut =>
      SimTimeout(100000)
      dut.clockDomain.forkStimulus(10)
      dut.io.invalidate #= false
      dut.io.sampleRequest.valid #= false
      dut.io.sampleFetch.ready #= false
      dut.io.texRead.cmd.ready #= false
      dut.io.texRead.rsp.valid #= false
      dut.io.texRead.rsp.last #= false
      dut.io.texRead.rsp.fragment.data #= 0
      dut.io.texRead.rsp.fragment.source #= 0
      setPoint(dut, 0)
      dut.clockDomain.waitSampling(8)

      var fills = 0
      var memoryFinished = 0
      fork {
        while (true) {
          dut.clockDomain.waitSamplingWhere(dut.io.texRead.cmd.valid.toBoolean)
          val base = dut.io.texRead.cmd.address.toInt
          val length = dut.io.texRead.cmd.length.toInt
          assert(length == c.texFillLineWords * 4 - 1)
          // Slave waits for a real request, then stalls its command.
          for (_ <- 0 until 4) {
            dut.clockDomain.waitSampling()
            assert(dut.io.texRead.cmd.valid.toBoolean)
            assert(dut.io.texRead.cmd.address.toInt == base)
          }
          dut.clockDomain.waitFallingEdge()
          dut.io.texRead.cmd.ready #= true
          dut.clockDomain.waitSampling()
          fills += 1
          dut.clockDomain.waitFallingEdge()
          dut.io.texRead.cmd.ready #= false
          for (beat <- 0 until c.texFillLineWords) {
            dut.clockDomain.waitSampling(1 + beat % 3)
            dut.clockDomain.waitFallingEdge()
            dut.io.texRead.rsp.valid #= true
            dut.io.texRead.rsp.fragment.data #= (((0xb000L + beat) << 16) | (0x1000L + beat))
            dut.io.texRead.rsp.last #= (beat == c.texFillLineWords - 1)
            sleep(1)
            dut.clockDomain.waitSamplingWhere(dut.io.texRead.rsp.ready.toBoolean)
            dut.clockDomain.waitFallingEdge()
            dut.io.texRead.rsp.valid #= false
            dut.io.texRead.rsp.last #= false
          }
          memoryFinished += 1
        }
      }

      def sample(address: Int, expected: Int): Int = {
        dut.clockDomain.waitFallingEdge()
        setPoint(dut, address)
        dut.io.sampleRequest.valid #= true
        sleep(1)
        dut.clockDomain.waitSamplingWhere(dut.io.sampleRequest.ready.toBoolean)
        dut.clockDomain.waitFallingEdge()
        dut.io.sampleRequest.valid #= false
        dut.clockDomain.waitSamplingWhere(dut.io.sampleFetch.valid.toBoolean)
        dut.clockDomain.waitFallingEdge()
        val value = dut.io.sampleFetch.payload.texels(0).toInt
        assert(value == expected,
          f"address0x$address%x returned0x$value%04x instead of filling texel0x$expected%04x")
        // A response held by the consumer must retain the correct texel.
        for (_ <- 0 until 7) {
          assert(dut.io.sampleFetch.valid.toBoolean)
          assert(dut.io.sampleFetch.payload.texels(0).toInt == expected)
          dut.clockDomain.waitSampling()
          dut.clockDomain.waitFallingEdge()
        }
        dut.io.sampleFetch.ready #= true
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
        dut.io.sampleFetch.ready #= false
        value
      }

      val coldFirst = sample(0, 0x1000)
      dut.clockDomain.waitSamplingWhere(memoryFinished == 1)
      assert(sample(0, 0x1000) == coldFirst)
      assert(fills == 1, "identical request must reuse its filled cache line")
      // New line, upper half of its fourth beat: catches a non-startup capture.
      val coldLater = sample(0x8e, 0xb003)
      dut.clockDomain.waitSamplingWhere(memoryFinished == 2)
      assert(sample(0x8e, 0xb003) == coldLater)
      assert(fills == 2, "later hit must not issue another fill")
    }
  }
}
