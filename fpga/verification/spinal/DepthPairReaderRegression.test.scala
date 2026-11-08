package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core._
import spinal.core.sim._
import voodoo.Config
import voodoo.framebuffer.FramebufferPlanePairReader
import scala.collection.mutable

class DepthPairReaderRegression extends AnyFunSuite {
  private def exercise(latency: Int, sourceGap: Int, stalls: Boolean): Unit = {
    SimConfig.withIVerilog.compile(FramebufferPlanePairReader(Config.voodoo1())).doSim { dut =>
      SimTimeout(40000)
      dut.clockDomain.forkStimulus(10)
      dut.io.readReq.valid #= false
      dut.io.readReq.address #= 0
      dut.io.readRsp.ready #= false
      dut.io.mem.cmd.ready #= false
      dut.io.mem.rsp.valid #= false
      dut.io.mem.rsp.last #= true
      dut.io.mem.rsp.opcode #= 0
      dut.io.mem.rsp.data #= 0
      dut.io.mem.rsp.context #= 0
      dut.clockDomain.waitSampling(8)
      // Forward/reverse pairs, repeated same-lane reads, isolated words.
      val requests = (0 until 12).flatMap { n =>
        val base = n * 32
        Seq(base, base + 2, base + 6, base + 4, base + 8, base + 8,
          base + 12, base + 16, base + 18, base + 20)
      }
      val unissued = mutable.Queue.empty[Int]
      val expected = mutable.Queue.empty[BigInt]
      val responses = mutable.Queue.empty[(Int, BigInt)]
      var sent, received, cycle, reads, merged, nextSource = 0
      var commandHeld: Option[BigInt] = None
      var outputHeld: Option[BigInt] = None
      def contents(address: Int, serial: Int): BigInt =
        BigInt(((address.toLong * 0x10203L) ^ (serial.toLong * 0x1f351L) ^ 0xa5c35a3cL) & 0xffffffffL)
      while (received < requests.size && cycle < 2500) {
        dut.clockDomain.waitFallingEdge()
        dut.io.readReq.valid #= (sent < requests.size && cycle >= nextSource)
        dut.io.readReq.address #= (if (sent < requests.size) requests(sent) else 0)
        dut.io.readRsp.ready #= (!stalls || (cycle >= 40 && cycle % 7 != 0))
        dut.io.mem.cmd.ready #= false
        dut.io.mem.rsp.valid #= false
        sleep(1)
        dut.io.mem.cmd.ready #= (!stalls || (dut.io.mem.cmd.valid.toBoolean && cycle % 5 != 0))
        sleep(1)
        val returning = responses.headOption.filter(_._1 <= cycle)
        val immediate = latency == 0 && responses.isEmpty &&
          dut.io.mem.cmd.valid.toBoolean && dut.io.mem.cmd.ready.toBoolean
        val immediateWord = if (immediate) contents(dut.io.mem.cmd.address.toInt, reads) else BigInt(0)
        dut.io.mem.rsp.valid #= (returning.nonEmpty || immediate)
        dut.io.mem.rsp.data #= returning.map(_._2).getOrElse(immediateWord)
        sleep(1)
        val input = dut.io.readReq.valid.toBoolean && dut.io.readReq.ready.toBoolean
        val command = dut.io.mem.cmd.valid.toBoolean && dut.io.mem.cmd.ready.toBoolean
        val response = dut.io.mem.rsp.valid.toBoolean && dut.io.mem.rsp.ready.toBoolean
        val output = dut.io.readRsp.valid.toBoolean && dut.io.readRsp.ready.toBoolean
        commandHeld.foreach { old =>
          assert(dut.io.mem.cmd.valid.toBoolean && dut.io.mem.cmd.address.toBigInt == old,
            "word address changed under memory backpressure")
        }
        commandHeld = if (dut.io.mem.cmd.valid.toBoolean && !dut.io.mem.cmd.ready.toBoolean)
          Some(dut.io.mem.cmd.address.toBigInt) else None
        outputHeld.foreach { old =>
          assert(dut.io.readRsp.valid.toBoolean && dut.io.readRsp.data.toBigInt == old,
            "halfword changed under consumer backpressure")
        }
        outputHeld = if (dut.io.readRsp.valid.toBoolean && !dut.io.readRsp.ready.toBoolean)
          Some(dut.io.readRsp.data.toBigInt) else None
        if (sent > received) assert(dut.io.busy.toBoolean, "busy cleared with accepted pixels pending")
        if (input) unissued.enqueue(requests(sent))
        if (command) {
          assert(unissued.nonEmpty)
          val first = unissued.dequeue()
          val address = first & ~3
          assert(dut.io.mem.cmd.address.toInt == address)
          assert(dut.io.mem.cmd.length.toInt == 3 && dut.io.mem.cmd.last.toBoolean)
          assert(dut.io.mem.cmd.opcode.toInt == 0)
          // Distinct contents for every real read detect reuse after issue,
          // even for repeated requests to the same address.
          val word = contents(address, reads)
          def half(request: Int): BigInt = (word >> (if ((request & 2) != 0) 16 else 0)) & 0xffff
          expected.enqueue(half(first))
          if (unissued.headOption.exists(a => (a & ~3) == address && (a & 2) != (first & 2))) {
            expected.enqueue(half(unissued.dequeue())); merged += 1
          }
          if (!immediate || !response) responses.enqueue((cycle + latency, word))
          reads += 1
        }
        if (output) {
          assert(expected.nonEmpty, "pixel returned before its memory read")
          assert(dut.io.readRsp.data.toBigInt == expected.dequeue(), s"wrong halfword at pixel $received")
        }
        dut.clockDomain.waitSampling()
        if (response && returning.nonEmpty) responses.dequeue()
        if (input) { sent += 1; nextSource = cycle + sourceGap }
        if (output) received += 1
        cycle += 1
      }
      assert(received == requests.size && unissued.isEmpty && expected.isEmpty && responses.isEmpty)
      if (sourceGap == 1) assert(merged >= 20, "continuous opposite lanes did not combine")
      if (sourceGap >= 3 && !stalls) assert(merged == 0, "an already-issued read satisfied a later request")
      dut.clockDomain.waitFallingEdge()
      dut.io.readReq.valid #= false
      dut.io.mem.rsp.valid #= false
      dut.clockDomain.waitSampling(10)
      assert(!dut.io.busy.toBoolean)
      println(s"PASS pair reader: pixels=$received words=$reads merged=$merged cycles=$cycle latency=$latency")
    }
  }
  test("adjacent halfwords combine before issue, retaining order through both kinds of stalls") {
    exercise(16, 1, true)
  }
  test("a later halfword never reuses an already-issued word") { exercise(0, 3, false) }
  test("continuous forward and reverse pairs work with immediate-ready memory") { exercise(0, 1, false) }
}
