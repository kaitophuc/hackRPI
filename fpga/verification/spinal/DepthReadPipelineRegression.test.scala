package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core._
import spinal.core.sim._
import spinal.lib.bus.bmb._
import voodoo.de10.De10PipelinedWordReader
import scala.collection.mutable

class DepthReadPipelineRegression extends AnyFunSuite {
  private def component(contextWidth: Int) = De10PipelinedWordReader(
    BmbParameter(addressWidth = 10, dataWidth = 32, sourceWidth = 0,
      contextWidth = contextWidth, lengthWidth = 4, canRead = true, canWrite = true,
      alignment = BmbParameter.BurstAlignement.BYTE),
    avalonAddressWidth = 12, addressBase = 0x100, addressMask = 0x3ff, slots = 8)

  private def data(address: Long): BigInt = BigInt((address * 0x10203L ^ 0xa5c35a3cL) & 0xffffffffL)

  private def exercise(contextWidth: Int, latency: Int): Unit = {
    SimConfig.withIVerilog.compile(component(contextWidth)).doSim { dut =>
      SimTimeout(20000)
      dut.clockDomain.forkStimulus(10)
      dut.io.bmb.cmd.valid #= false
      dut.io.bmb.cmd.last #= true
      dut.io.bmb.cmd.opcode #= 0
      dut.io.bmb.cmd.address #= 0
      dut.io.bmb.cmd.length #= 3
      dut.io.bmb.cmd.data #= 0
      dut.io.bmb.cmd.mask #= 15
      if (contextWidth > 0) dut.io.bmb.cmd.context #= 0
      dut.io.bmb.rsp.ready #= false
      dut.io.mem.waitRequestn #= false
      dut.io.mem.readDataValid #= false
      dut.io.mem.readData #= 0
      dut.clockDomain.waitSampling(8)

      val count = 64
      var sent, received, cycle, maximumPending = 0
      val pending = mutable.Queue.empty[(Int, BigInt)]
      var stalledMemory: Option[Long] = None
      var stalledResponse: Option[(BigInt, Int)] = None
      while (received < count && cycle < 800) {
        dut.clockDomain.waitFallingEdge()
        dut.io.bmb.cmd.valid #= (sent < count)
        dut.io.bmb.cmd.address #= (sent % count) * 4
        if (contextWidth > 0) dut.io.bmb.cmd.context #= sent % 32
        dut.io.bmb.rsp.ready #= (cycle >= 40 && cycle % 7 != 0)
        // Request-dependent grant catches illegal read-valid/waitrequest coupling.
        dut.io.mem.waitRequestn #= false
        dut.io.mem.readDataValid #= false
        sleep(1)
        dut.io.mem.waitRequestn #= (dut.io.mem.read.toBoolean && cycle % 5 != 0)
        sleep(1)
        val launch = dut.io.mem.read.toBoolean && dut.io.mem.waitRequestn.toBoolean
        val address = if (dut.io.mem.read.toBoolean) dut.io.mem.address.toLong else 0L
        val returning = pending.headOption.filter(_._1 <= cycle)
        val immediate = latency == 0 && launch && returning.isEmpty
        dut.io.mem.readDataValid #= (returning.nonEmpty || immediate)
        dut.io.mem.readData #= returning.map(_._2).getOrElse(if (immediate) data(address) else BigInt(0))
        sleep(1)

        val accept = dut.io.bmb.cmd.valid.toBoolean && dut.io.bmb.cmd.ready.toBoolean
        val reply = dut.io.bmb.rsp.valid.toBoolean && dut.io.bmb.rsp.ready.toBoolean
        assert(!dut.io.mem.write.toBoolean)
        if (launch) {
          assert(dut.io.mem.burstCount.toInt == 1)
          assert(dut.io.mem.byteEnable.toInt == 15)
          assert(address >= 0x100 && address < 0x200)
        }
        stalledMemory.foreach { old =>
          assert(dut.io.mem.read.toBoolean, "read vanished before Avalon acceptance")
          assert(address == old, "address changed under Avalon stall")
        }
        stalledMemory = if (dut.io.mem.read.toBoolean && !dut.io.mem.waitRequestn.toBoolean) Some(address) else None
        val responseContext = if (contextWidth > 0 && dut.io.bmb.rsp.valid.toBoolean) dut.io.bmb.rsp.context.toInt else 0
        stalledResponse.foreach { old =>
          assert(dut.io.bmb.rsp.valid.toBoolean)
          assert((dut.io.bmb.rsp.data.toBigInt, responseContext) == old,
            "BMB response changed under consumer backpressure")
        }
        stalledResponse = if (dut.io.bmb.rsp.valid.toBoolean && !dut.io.bmb.rsp.ready.toBoolean)
          Some((dut.io.bmb.rsp.data.toBigInt, responseContext)) else None
        if (sent > received) assert(dut.io.publicationBusy.toBoolean,
          "publication became idle with accepted responses still outstanding")
        if (reply) {
          assert(dut.io.bmb.rsp.last.toBoolean)
          assert(dut.io.bmb.rsp.data.toBigInt == data(0x100 + received * 4))
          if (contextWidth > 0) assert(responseContext == received % 32)
        }
        dut.clockDomain.waitSampling()
        if (returning.nonEmpty) pending.dequeue()
        if (launch && !immediate) pending.enqueue((cycle + latency, data(address)))
        maximumPending = maximumPending.max(pending.size)
        if (accept) sent += 1
        if (reply) received += 1
        assert(sent - received <= 8, "response storage was overcommitted")
        cycle += 1
      }
      assert(received == count, s"only $received/$count responses after $cycle cycles")
      assert(pending.isEmpty)
      if (latency > 0) assert(maximumPending >= 4, "reads did not overlap")
      dut.clockDomain.waitFallingEdge()
      dut.io.bmb.cmd.valid #= false
      dut.io.mem.readDataValid #= false
      dut.clockDomain.waitSampling(8)
      assert(!dut.io.publicationBusy.toBoolean)
      println(s"PASS depth reader contexts=$contextWidth latency=$latency: $count ordered responses, cycles=$cycle, maxDDRPending=$maximumPending")
    }
  }

  test("multiple depth reads retain ordered contexts through memory and consumer stalls") { exercise(5, 16) }
  test("context-free reads and immediate Avalon responses remain ordered") { exercise(0, 0) }
}
