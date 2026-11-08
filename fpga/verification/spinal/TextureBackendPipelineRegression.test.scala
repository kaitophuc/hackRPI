package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core.sim._
import voodoo.Config
import voodoo.de10.{De10AddressMap, De10MemBackend}

/** Exercise the real texture source-remover, forward register and Avalon adapter. */
class TextureBackendPipelineRegression extends AnyFunSuite {
  test("texture commands register before Avalon, retain payload under stalls and stay busy until responses drain") {
    val c = Config.voodoo1().copy(memBurstLengthWidth = 6)
    SimConfig.withIVerilog.compile(De10MemBackend(c)).doSim { dut =>
      SimTimeout(100000)
      dut.clockDomain.forkStimulus(10)
      val inputs = Seq(dut.io.fbMemWrite, dut.io.fbColorWriteMem, dut.io.fbAuxWriteMem,
        dut.io.fbColorReadMem, dut.io.fbAuxReadMem, dut.io.texMem)
      inputs.foreach { bus =>
        bus.cmd.valid #= false
        bus.cmd.last #= true
        bus.cmd.opcode #= 1
        bus.cmd.source #= 0
        bus.cmd.address #= 0
        bus.cmd.length #= 3
        bus.cmd.data #= 0
        bus.cmd.mask #= 15
        bus.rsp.ready #= true
      }
      val outputs = Seq(dut.io.memFbWrite, dut.io.memFbColorWrite, dut.io.memFbAuxWrite,
        dut.io.memFbColorRead, dut.io.memFbAuxRead, dut.io.memTex)
      outputs.foreach { bus =>
        bus.waitRequestn #= false
        bus.readDataValid #= false
        bus.readData #= 0
      }
      val command = dut.io.texMem.cmd
      val response = dut.io.texMem.rsp
      val memory = dut.io.memTex
      response.ready #= false
      dut.clockDomain.waitSampling(8)
      dut.clockDomain.waitFallingEdge()
      assert(!dut.io.publicationBusy.toBoolean)

      val writes = Seq((0x40, 0x1234abcdL, 5, 3), (0x84, 0xdeadbeefL, 10, 7))
      val accepted = scala.collection.mutable.ArrayBuffer.empty[(Long, Long, Int)]
      val replies = scala.collection.mutable.ArrayBuffer.empty[Int]
      fork {
        while (true) {
          dut.clockDomain.waitSampling()
          if (memory.write.toBoolean && memory.waitRequestn.toBoolean) {
            accepted += ((memory.address.toLong, memory.writeData.toLong, memory.byteEnable.toInt))
            assert(memory.burstCount.toInt == 1)
          }
          if (response.valid.toBoolean && response.ready.toBoolean) replies += response.source.toInt
        }
      }

      // Empty forward register accepts a command while the memory refuses it.
      command.address #= writes.head._1
      command.data #= writes.head._2
      command.mask #= writes.head._3
      command.source #= writes.head._4
      command.valid #= true
      sleep(1)
      assert(command.ready.toBoolean, "empty texture command register must accept under Avalon stall")
      assert(!memory.write.toBoolean, "new texture command must cross a clocked boundary before Avalon")
      assert(dut.io.publicationBusy.toBoolean)
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitFallingEdge()
      command.valid #= false
      command.address #= 0x3fc
      command.data #= 0x55555555L
      command.mask #= 15
      command.source #= 31
      sleep(1)
      for (_ <- 0 until 6) {
        assert(memory.write.toBoolean)
        assert(memory.address.toLong == De10AddressMap.texMemBase + writes.head._1)
        assert(memory.writeData.toLong == writes.head._2)
        assert(memory.byteEnable.toInt == writes.head._3)
        assert(dut.io.publicationBusy.toBoolean, "registered but unaccepted command is outstanding")
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
      }

      // Present the next source/payload while the first command is still held.
      command.address #= writes(1)._1
      command.data #= writes(1)._2
      command.mask #= writes(1)._3
      command.source #= writes(1)._4
      command.valid #= true
      memory.waitRequestn #= true
      sleep(1)
      var secondEnqueued = command.ready.toBoolean
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitFallingEdge()
      if (secondEnqueued) command.valid #= false
      memory.waitRequestn #= false
      dut.clockDomain.waitSampling(3)
      assert(accepted.size == 1)
      assert(response.valid.toBoolean)
      assert(response.source.toInt == writes.head._4)
      assert(dut.io.publicationBusy.toBoolean, "held BMB response must block publication")
      for (_ <- 0 until 4) {
        dut.clockDomain.waitSampling()
        assert(response.valid.toBoolean)
        assert(response.source.toInt == writes.head._4)
        assert(dut.io.publicationBusy.toBoolean)
      }

      dut.clockDomain.waitFallingEdge()
      response.ready #= true
      memory.waitRequestn #= true
      while (!secondEnqueued) {
        sleep(1)
        secondEnqueued = command.ready.toBoolean
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
      }
      command.valid #= false
      dut.clockDomain.waitSamplingWhere(accepted.size == 2 && replies.size == 2)
      dut.clockDomain.waitSampling(5)
      assert(accepted.toSeq == writes.map { case (addr, data, mask, _) =>
        (De10AddressMap.texMemBase.toLong + addr, data, mask) })
      assert(replies.toSeq == writes.map(_._4), "source IDs/order must survive the registered path")
      assert(!dut.io.publicationBusy.toBoolean, "publication may clear only after responses drain")

      // A queued four-beat texture read remains busy through delayed response beats.
      dut.clockDomain.waitFallingEdge()
      memory.waitRequestn #= false
      response.ready #= false
      command.opcode #= 0
      command.address #= 0x100
      command.length #= 15
      command.source #= 11
      command.valid #= true
      sleep(1)
      assert(command.ready.toBoolean)
      assert(!memory.read.toBoolean)
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitFallingEdge()
      command.valid #= false
      dut.clockDomain.waitSamplingWhere(memory.read.toBoolean)
      dut.clockDomain.waitFallingEdge()
      for (_ <- 0 until 5) {
        assert(memory.read.toBoolean)
        assert(memory.address.toLong == De10AddressMap.texMemBase + 0x100)
        assert(memory.burstCount.toInt == 4)
        assert(dut.io.publicationBusy.toBoolean)
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
      }
      memory.waitRequestn #= true
      dut.clockDomain.waitSampling()
      dut.clockDomain.waitFallingEdge()
      memory.waitRequestn #= false
      val expected = Seq(0x1010L, 0x2020L, 0x3030L, 0x4040L)
      expected.foreach { word =>
        dut.clockDomain.waitSampling(2)
        assert(dut.io.publicationBusy.toBoolean)
        dut.clockDomain.waitFallingEdge()
        memory.readDataValid #= true
        memory.readData #= word
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
        memory.readDataValid #= false
      }
      dut.clockDomain.waitSampling(3)
      expected.zipWithIndex.foreach { case (word, beat) =>
        dut.clockDomain.waitFallingEdge()
        sleep(1)
        assert(response.valid.toBoolean)
        assert(response.data.toLong == word)
        assert(response.source.toInt == 11)
        assert(response.last.toBoolean == (beat == expected.size - 1))
        assert(dut.io.publicationBusy.toBoolean)
        dut.clockDomain.waitSampling(2)
        assert(response.data.toLong == word)
        response.ready #= true
        dut.clockDomain.waitSampling()
        dut.clockDomain.waitFallingEdge()
        response.ready #= false
      }
      dut.clockDomain.waitSampling(5)
      assert(!dut.io.publicationBusy.toBoolean)
      assert(!memory.read.toBoolean && !memory.write.toBoolean)
    }
  }
}
