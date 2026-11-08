package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core.sim._
import voodoo.Config
import voodoo.bus.{PciFifo, RegisterCategory}
import voodoo.frontend.RegisterBank

class FifoSyncRegression extends AnyFunSuite {
  test("sync color write rechecks busy after the registered issue stage") {
    val params = RegisterBank.bmbParams(Config.voodoo1())
    SimConfig.withIVerilog.compile(PciFifo(params,
      Map(BigInt(0x80) -> RegisterCategory.fifoNoSync,
          BigInt(0x144) -> RegisterCategory.fifoWithSync),
      Map.empty, Seq(BigInt(0x80)))).doSim { dut =>
      SimTimeout(10000)
      dut.clockDomain.forkStimulus(10)
      dut.io.pipelineBusy #= false
      dut.io.commandReady.foreach(_ #= true)
      dut.io.wasEnqueuedAddr #= 0x80
      dut.io.cpuSide.cmd.valid #= false
      dut.io.cpuSide.cmd.last #= true
      dut.io.cpuSide.cmd.source #= 0
      dut.io.cpuSide.cmd.opcode #= 1
      dut.io.cpuSide.cmd.address #= 0
      dut.io.cpuSide.cmd.length #= 3
      dut.io.cpuSide.cmd.data #= 0
      dut.io.cpuSide.cmd.mask #= 15
      dut.io.cpuSide.rsp.ready #= true
      dut.io.regSide.cmd.ready #= false
      dut.io.regSide.rsp.valid #= false
      dut.io.regSide.rsp.last #= true
      dut.io.regSide.rsp.source #= 0
      dut.io.regSide.rsp.opcode #= 0
      dut.io.regSide.rsp.data #= 0
      dut.io.texWrite.valid #= false
      dut.io.texWrite.pciAddr #= 0
      dut.io.texWrite.data #= 0
      dut.io.texWrite.mask #= 0
      dut.io.texDrain.ready #= true
      dut.clockDomain.waitSampling(5)

      def enqueue(address: Int, data: Long): Unit = {
        dut.clockDomain.waitFallingEdge()
        dut.io.cpuSide.cmd.address #= address
        dut.io.cpuSide.cmd.data #= data
        dut.io.cpuSide.cmd.valid #= true
        sleep(1)
        var waits = 0
        while(!dut.io.cpuSide.cmd.ready.toBoolean && waits < 40) {
          dut.clockDomain.waitSampling(); waits += 1
        }
        assert(waits < 40)
        dut.clockDomain.waitSampling()
        dut.io.cpuSide.cmd.valid #= false
      }
      enqueue(0x80, 0)
      enqueue(0x144, 0x000000ffL)
      dut.clockDomain.waitSampling(10)
      assert(dut.io.regSide.cmd.valid.toBoolean)
      assert(dut.io.regSide.cmd.address.toInt == 0x80)
      dut.clockDomain.waitFallingEdge()
      dut.io.regSide.cmd.ready #= true
      dut.clockDomain.waitSampling() // triangle commits, next write can enter issue stage
      dut.clockDomain.waitFallingEdge()
      dut.io.pipelineBusy #= true // command reaches the registered render input
      sleep(1)
      for (_ <- 0 until 6) {
        assert(!dut.io.regSide.cmd.valid.toBoolean,
          "sync color write committed while the prior triangle was busy")
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
      }
      dut.io.pipelineBusy #= false
      sleep(1)
      assert(dut.io.regSide.cmd.valid.toBoolean)
      assert(dut.io.regSide.cmd.address.toInt == 0x144)
      assert(dut.io.regSide.cmd.data.toLong == 0xffL)
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitSampling(5)
      assert(!dut.io.regSide.cmd.valid.toBoolean)

      // A command's destination may also stop accepting after issue. Recheck
      // commandReady at commit instead of dropping the already-staged command.
      dut.io.regSide.cmd.ready #= false
      enqueue(0x80, 1)
      dut.clockDomain.waitSampling(8)
      assert(dut.io.regSide.cmd.valid.toBoolean)
      dut.clockDomain.waitFallingEdge()
      dut.io.commandReady(0) #= false
      dut.io.regSide.cmd.ready #= true
      sleep(1)
      for (_ <- 0 until 4) {
        assert(!dut.io.regSide.cmd.valid.toBoolean,
          "staged triangle ignored destination command backpressure")
        dut.clockDomain.waitSampling()
      }
      dut.clockDomain.waitFallingEdge()
      dut.io.commandReady(0) #= true
      sleep(1)
      assert(dut.io.regSide.cmd.valid.toBoolean)
      assert(dut.io.regSide.cmd.address.toInt == 0x80)
      assert(dut.io.regSide.cmd.data.toLong == 1)
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitSampling(5)
      assert(!dut.io.regSide.cmd.valid.toBoolean)
    }
  }
}
