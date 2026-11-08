package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core._
import spinal.core.sim._
import spinal.lib.bus.bmb._
import voodoo.de10.De10BmbToAvalonMm

/** A legal Avalon slave may wait for a request before granting it. */
class BridgeReadRegression extends AnyFunSuite {
  private def bridge = De10BmbToAvalonMm(
    BmbParameter(addressWidth = 10, dataWidth = 32, sourceWidth = 0,
      contextWidth = 1, lengthWidth = 4, canRead = true, canWrite = true,
      alignment = BmbParameter.BurstAlignement.BYTE),
    avalonAddressWidth = 12, addressBase = 0x100, addressMask = 0x3ff)

  private def setup(dut: De10BmbToAvalonMm): Unit = {
    SimTimeout(10000)
    dut.clockDomain.forkStimulus(10)
    dut.io.bmb.cmd.valid #= false
    dut.io.bmb.cmd.last #= true
    dut.io.bmb.cmd.opcode #= 0
    dut.io.bmb.cmd.context #= 0
    dut.io.bmb.cmd.address #= 0x40
    dut.io.bmb.cmd.length #= 15
    dut.io.bmb.cmd.data #= 0x12345678
    dut.io.bmb.cmd.mask #= 15
    dut.io.bmb.rsp.ready #= false
    dut.io.mem.waitRequestn #= false
    dut.io.mem.readDataValid #= false
    dut.io.mem.readData #= 0
    dut.clockDomain.waitSampling(5)
  }

  test("queued burst read asserts and holds before ready, then returns every beat under BMB stalls") {
    SimConfig.withIVerilog.compile(bridge).doSim { dut =>
      setup(dut)
      dut.io.bmb.cmd.valid #= true
      sleep(1)
      assert(dut.io.bmb.cmd.ready.toBoolean)
      dut.clockDomain.waitSampling()
      dut.io.bmb.cmd.valid #= false
      dut.clockDomain.waitFallingEdge()
      // The old adapter gated read with ready and deadlocked this slave.
      for (_ <- 0 until 7) {
        assert(dut.io.mem.read.toBoolean, "read must assert while waitrequest is high")
        assert(!dut.io.mem.write.toBoolean)
        assert(dut.io.mem.address.toInt == 0x140)
        assert(dut.io.mem.burstCount.toInt == 4)
        assert(dut.io.mem.byteEnable.toInt == 15)
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
      }
      dut.io.mem.waitRequestn #= true
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitFallingEdge()
      dut.io.mem.waitRequestn #= false
      assert(!dut.io.mem.read.toBoolean, "accepted read was issued twice")
      val expected = Seq(0x10203040L, 0xabcdef01L, 0x87654321L, 0x55667788L)
      expected.foreach { data =>
        dut.io.mem.readDataValid #= true
        dut.io.mem.readData #= data
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
      }
      dut.io.mem.readDataValid #= false
      dut.clockDomain.waitSampling(3)
      expected.zipWithIndex.foreach { case (data, index) =>
        dut.clockDomain.waitFallingEdge()
        sleep(1)
        assert(dut.io.bmb.rsp.valid.toBoolean)
        assert(dut.io.bmb.rsp.data.toLong == data)
        assert(dut.io.bmb.rsp.last.toBoolean == (index == expected.size - 1))
        dut.clockDomain.waitSampling(2) // hold each response under backpressure
        assert(dut.io.bmb.rsp.data.toLong == data)
        dut.io.bmb.rsp.ready #= true
        dut.clockDomain.waitSampling()
        dut.io.bmb.rsp.ready #= false
      }
      dut.clockDomain.waitSampling(3)
      assert(!dut.io.bmb.rsp.valid.toBoolean)
      assert(!dut.io.mem.read.toBoolean)
    }
  }

  test("write request and payload hold before ready and produce one acknowledgement") {
    SimConfig.withIVerilog.compile(bridge).doSim { dut =>
      setup(dut)
      dut.io.bmb.cmd.opcode #= 1
      dut.io.bmb.cmd.length #= 3
      dut.io.bmb.cmd.mask #= 5
      dut.io.bmb.cmd.valid #= true
      sleep(1)
      for (_ <- 0 until 7) {
        assert(dut.io.mem.write.toBoolean, "write must assert while waitrequest is high")
        assert(!dut.io.bmb.cmd.ready.toBoolean)
        assert(dut.io.mem.address.toInt == 0x140)
        assert(dut.io.mem.writeData.toLong == 0x12345678L)
        assert(dut.io.mem.byteEnable.toInt == 5)
        assert(dut.io.mem.burstCount.toInt == 1)
        assert(!dut.io.bmb.rsp.valid.toBoolean)
        dut.clockDomain.waitSampling()
      }
      dut.clockDomain.waitFallingEdge()
      dut.io.mem.waitRequestn #= true
      sleep(1)
      assert(dut.io.bmb.cmd.ready.toBoolean)
      dut.clockDomain.waitSampling()
      dut.io.bmb.cmd.valid #= false
      dut.clockDomain.waitFallingEdge()
      dut.io.mem.waitRequestn #= false
      assert(!dut.io.mem.write.toBoolean)
      assert(dut.io.bmb.rsp.valid.toBoolean)
      assert(dut.io.bmb.rsp.last.toBoolean)
      dut.clockDomain.waitSampling(4)
      dut.io.bmb.rsp.ready #= true
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitFallingEdge()
      assert(!dut.io.bmb.rsp.valid.toBoolean)
    }
  }
}
