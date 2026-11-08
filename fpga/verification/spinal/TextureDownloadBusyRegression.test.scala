package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core._
import spinal.core.sim._
import spinal.lib._
import voodoo.Config
import voodoo.bus.TexWritePayload
import voodoo.texture.TextureMem

case class TextureDownloadBusyHarness(c: Config) extends Component {
  val io = new Bundle {
    val drain = slave(Stream(TexWritePayload()))
    val config = in(TextureMem.DownloadConfig(c))
    val write = master(Stream(TextureMem.WriteCmd(c)))
    val busy = out Bool ()
  }
  io.write << TextureMem.WriteCmd.fromPciDrain(c, io.drain, io.config, io.busy)
}

/** No idle gap is permitted between the accepted PCI drain and backend command. */
class TextureDownloadBusyRegression extends AnyFunSuite {
  for (packed <- Seq(true, false)) {
    test(s"download busy covers first preparation stage and held output, packed=$packed") {
      val c = Config.voodoo1().copy(packedTexLayout = packed)
      SimConfig.withIVerilog.compile(TextureDownloadBusyHarness(c)).doSim { dut =>
        SimTimeout(10000)
        dut.clockDomain.forkStimulus(10)
        dut.io.drain.valid #= false
        dut.io.drain.pciAddr #= 0
        dut.io.drain.data #= 0x1234abcdL
        dut.io.drain.mask #= 5
        dut.io.config.textureMode #= 0xa00 // RGB565
        dut.io.config.texBaseAddr #= 0
        dut.io.config.texBaseAddr1 #= 0
        dut.io.config.texBaseAddr2 #= 0
        dut.io.config.texBaseAddr38 #= 0
        dut.io.config.tLOD #= 0
        dut.io.write.ready #= false
        dut.clockDomain.waitSampling(5)
        dut.clockDomain.waitFallingEdge()
        assert(!dut.io.busy.toBoolean)
        dut.io.drain.valid #= true
        sleep(1)
        assert(dut.io.drain.ready.toBoolean)
        assert(!dut.io.busy.toBoolean, "busy must use registered occupancy, not input-valid feedthrough")
        dut.clockDomain.waitSampling() // E0: final PCI texture drain accepted
        dut.clockDomain.waitFallingEdge()
        dut.io.drain.valid #= false
        sleep(1)
        assert(!dut.io.write.valid.toBoolean, "backend command is not visible in the first preparation cycle")
        assert(dut.io.busy.toBoolean,
          "first preparation register must prevent following sync/state commit before E1")
        dut.clockDomain.waitSampling() // E1: command enters second register
        dut.clockDomain.waitFallingEdge()
        assert(dut.io.write.valid.toBoolean)
        assert(dut.io.busy.toBoolean)
        dut.io.drain.pciAddr #= 0x1fc
        dut.io.drain.data #= 0x77777777L
        dut.io.drain.mask #= 15
        for (_ <- 0 until 6) {
          assert(dut.io.write.valid.toBoolean)
          assert(dut.io.write.address.toInt == 0)
          assert(dut.io.write.data.toLong == 0x1234abcdL)
          assert(dut.io.write.mask.toInt == 5)
          assert(dut.io.busy.toBoolean, "held output register must keep sync/publication blocked")
          dut.clockDomain.waitSampling()
          dut.clockDomain.waitFallingEdge()
        }
        dut.io.write.ready #= true
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
        assert(!dut.io.write.valid.toBoolean)
        assert(!dut.io.busy.toBoolean)

        // Invalid TMU selection is dropped, but cannot leave busy stuck high.
        dut.io.drain.pciAddr #= 0x200000
        dut.io.drain.valid #= true
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
        dut.io.drain.valid #= false
        assert(dut.io.busy.toBoolean)
        assert(!dut.io.write.valid.toBoolean)
        dut.clockDomain.waitSampling(3)
        assert(!dut.io.busy.toBoolean)
        assert(!dut.io.write.valid.toBoolean)
      }
    }
  }
}
