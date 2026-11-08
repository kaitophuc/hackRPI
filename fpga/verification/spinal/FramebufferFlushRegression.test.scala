package platformverification

import org.scalatest.funsuite.AnyFunSuite
import spinal.core._
import spinal.core.sim._
import spinal.lib._
import spinal.lib.bus.bmb._
import spinal.lib.bus.avalon._
import voodoo.{Config, TraceConfig}
import voodoo.framebuffer.FramebufferPlaneBuffer
import voodoo.de10.{De10BmbToAvalonMm, De10MemBackend}

/** Exercise the actual board adapter, whose accepted writes are single-beat. */
case class BufferWithBackend(c: Config) extends Component {
  val io = new Bundle {
    val writeReq = slave(Stream(FramebufferPlaneBuffer.WriteReq(c)))
    val flush = in Bool()
    val busy = out Bool()
    val drainCount = out UInt(32 bits)
    val flushCount = out UInt(32 bits)
    val fullCount = out UInt(32 bits)
    val partialCount = out UInt(32 bits)
    val memory = master(AvalonMM(De10MemBackend.avalonConfig(32)))
  }
  val buffer = FramebufferPlaneBuffer(c)
  val params = FramebufferPlaneBuffer.bmbParams(c)
  val remover = BmbSourceRemover(params)
  val bridge = De10BmbToAvalonMm(De10BmbToAvalonMm.singleSourceBridgeParams(params), 32, 0, 4095)
  buffer.io.readReq.valid := False
  buffer.io.readReq.address := 0
  buffer.io.readRsp.ready := True
  buffer.io.writeReq << io.writeReq
  buffer.io.flush := io.flush
  remover.io.input <> buffer.io.mem
  remover.io.output <> bridge.io.bmb
  io.memory <> bridge.io.mem
  io.busy := buffer.io.busy || bridge.io.publicationBusy ||
    remover.io.input.cmd.valid || remover.io.output.cmd.valid
  io.drainCount := buffer.io.writeDrainCount
  io.flushCount := buffer.io.writeDrainReasonFlushCount
  io.fullCount := buffer.io.writeFullDrainCount
  io.partialCount := buffer.io.writePartialDrainCount
}

/** Selected upstream write buffer: final partial runs, masks and memory stalls. */
class FramebufferFlushRegression extends AnyFunSuite {
  private def config = Config.voodoo1().copy(
    addressWidth = 12 bits, memBurstLengthWidth = 6,
    fbWriteBufferLineWords = 8, fbWriteBufferCount = 2,
    useFbWriteBuffer = true, useTexFillCache = false,
    trace = TraceConfig(enabled = true))

  private def setup(dut: BufferWithBackend): Array[Int] = {
    SimTimeout(100000)
    dut.clockDomain.forkStimulus(10)
    dut.io.writeReq.valid #= false
    dut.io.writeReq.address #= 0
    dut.io.writeReq.data #= 0
    dut.io.writeReq.mask #= 0
    dut.io.flush #= false
    val memory = Array.fill(1 << 12)(0)
    dut.io.memory.waitRequestn #= true
    dut.io.memory.readDataValid #= false
    dut.io.memory.readData #= 0
    val random = new scala.util.Random(0xde10)
    fork {
      while (true) {
        dut.clockDomain.waitFallingEdge()
        dut.io.memory.waitRequestn #= (random.nextInt(4) != 0)
      }
    }
    fork {
      while (true) {
        dut.clockDomain.waitSampling()
        assert(!dut.io.memory.read.toBoolean, "write-buffer backend unexpectedly issued a read")
        if (dut.io.memory.write.toBoolean && dut.io.memory.waitRequestn.toBoolean) {
          val address = dut.io.memory.address.toLong.toInt
          val data = dut.io.memory.writeData.toLong
          val mask = dut.io.memory.byteEnable.toInt
          assert(dut.io.memory.burstCount.toInt == 1)
          assert(address >= 0 && address + 4 <= memory.length)
          for (lane <- 0 until 4 if (mask & (1 << lane)) != 0)
            memory(address + lane) = ((data >> (lane * 8)) & 255).toInt
        }
      }
    }
    dut.clockDomain.waitSampling(5)
    memory
  }

  private def write(dut: BufferWithBackend, address: Int, data: Long, mask: Int = 15): Unit = {
    dut.io.writeReq.valid #= true
    dut.io.writeReq.address #= address
    dut.io.writeReq.data #= BigInt(data & 0xffffffffL)
    dut.io.writeReq.mask #= mask
    sleep(1)
    var wait = 0
    while (!dut.io.writeReq.ready.toBoolean && wait < 500) {
      dut.clockDomain.waitSampling(); wait += 1
    }
    assert(wait < 500, "write input stalled indefinitely")
    dut.clockDomain.waitSampling()
    dut.io.writeReq.valid #= false
  }

  private def flush(dut: BufferWithBackend): Unit = {
    dut.io.flush #= true
    dut.clockDomain.waitSampling(2)
    var wait = 0
    while (dut.io.busy.toBoolean && wait < 2000) {
      dut.clockDomain.waitSampling(); wait += 1
    }
    assert(wait < 2000, "flush did not complete under bounded memory stalls")
    dut.clockDomain.waitSampling(5)
    assert(!dut.io.busy.toBoolean, "flush completion was unstable")
  }

  private def word(memory: Array[Int], address: Int): Long = {
    (0 until 4).foldLeft(0L)((result, lane) => result | ((memory(address + lane) & 255L) << (lane * 8)))
  }

  test("one partial final word requires flush and reaches backing memory") {
    SimConfig.withIVerilog.compile(BufferWithBackend(config)).doSim { dut =>
      val memory = setup(dut)
      write(dut, 0x40, 0x1234abcdL)
      dut.clockDomain.waitSampling(25)
      assert(dut.io.drainCount.toLong == 0, "unexpected implicit publication")
      assert(!dut.io.busy.toBoolean, "upstream idle behavior changed; re-audit completion contract")
      flush(dut)
      assert(word(memory, 0x40) == 0x1234abcdL)
      assert(dut.io.flushCount.toLong >= 1)
    }
  }

  test("masked same-word merge and partial run survive randomized memory backpressure") {
    SimConfig.withIVerilog.compile(BufferWithBackend(config)).doSim { dut =>
      val memory = setup(dut)
      write(dut, 0x40, 0x00001234L, 3)
      write(dut, 0x40, 0xabcd0000L, 12)
      write(dut, 0x44, 0xdeadbeefL)
      write(dut, 0x48, 0x13572468L)
      flush(dut)
      assert(word(memory, 0x40) == 0xabcd1234L)
      assert(word(memory, 0x44) == 0xdeadbeefL)
      assert(word(memory, 0x48) == 0x13572468L)
    }
  }

  test("full runs and final partial run preserve every word under backpressure") {
    SimConfig.withIVerilog.compile(BufferWithBackend(config)).doSim { dut =>
      val memory = setup(dut)
      val expected = (0 until 35).map(i => (0x100 + i * 4, 0x80000100L + i))
      expected.foreach { case (address, data) => write(dut, address, data) }
      flush(dut)
      expected.foreach { case (address, data) => assert(word(memory, address) == data, s"wrong word at $address") }
      assert(dut.io.fullCount.toLong > 0)
      assert(dut.io.partialCount.toLong > 0)
    }
  }
}
