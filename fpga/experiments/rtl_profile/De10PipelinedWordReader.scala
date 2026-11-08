package voodoo.de10

import spinal.core._
import spinal.lib._
import spinal.lib.bus.avalon._
import spinal.lib.bus.bmb._

/** Ordered, uncached single-word reader for the direct depth-reader port.
  * Every accepted BMB request reserves a response slot before reaching DDR.
  * No depth value is reused; only independent memory transactions overlap.
  */
case class De10PipelinedWordReader(
    bmbParams: BmbParameter,
    avalonAddressWidth: Int,
    addressBase: BigInt,
    addressMask: BigInt,
    slots: Int = 8
) extends Component {
  De10BmbToAvalonMm.requireSingleSource(bmbParams)
  require(bmbParams.access.dataWidth == 32 && slots >= 2)
  require(addressBase >= 0 && addressBase + addressMask + 1 <= (BigInt(1) << avalonAddressWidth))
  private val contextWidth = bmbParams.access.contextWidth
  private val storedContextWidth = scala.math.max(1, contextWidth)
  private val inputAddressWidth = bmbParams.access.addressWidth

  val io = new Bundle {
    val bmb = slave(Bmb(bmbParams))
    val mem = master(AvalonMM(De10MemBackend.avalonConfig(avalonAddressWidth)))
    val publicationBusy = out Bool()
  }
  case class Command() extends Bundle {
    val address = UInt(avalonAddressWidth bits)
    val context = Bits(storedContextWidth bits)
  }
  case class Response() extends Bundle {
    val data = Bits(32 bits)
    val context = Bits(storedContextWidth bits)
  }
  val commands = StreamFifo(Command(), slots)
  val contexts = StreamFifo(Bits(storedContextWidth bits), slots)
  val responses = StreamFifo(Response(), slots)
  val inFlight = Reg(UInt(log2Up(slots + 1) bits)) init 0
  val supported = io.bmb.cmd.opcode === Bmb.Cmd.Opcode.READ &&
    io.bmb.cmd.length === 3 && io.bmb.cmd.address(1 downto 0) === 0
  val creditAvailable = inFlight < slots
  val localAddress = io.bmb.cmd.address & U(addressMask & ((BigInt(1) << inputAddressWidth) - 1), inputAddressWidth bits)
  commands.io.push.valid := io.bmb.cmd.valid && supported && creditAvailable
  commands.io.push.address := (localAddress.resize(avalonAddressWidth) + U(addressBase, avalonAddressWidth bits)).resized
  if (contextWidth > 0) commands.io.push.context := io.bmb.cmd.context
  else commands.io.push.context := 0
  io.bmb.cmd.ready := commands.io.push.ready && supported && creditAvailable

  io.mem.read := commands.io.pop.valid && contexts.io.push.ready
  io.mem.write := False
  io.mem.address := commands.io.pop.address
  io.mem.burstCount := 1
  io.mem.byteEnable := B(15, 4 bits)
  io.mem.writeData := 0
  val launched = io.mem.read && io.mem.waitRequestn
  commands.io.pop.ready := contexts.io.push.ready && io.mem.waitRequestn

  // A zero-latency legal slave may return the newly accepted request before
  // its context reaches the FIFO. All later responses use the ordered FIFO.
  val immediateResponse = io.mem.readDataValid && !contexts.io.pop.valid
  contexts.io.push.valid := launched && !immediateResponse
  contexts.io.push.payload := commands.io.pop.context
  contexts.io.pop.ready := io.mem.readDataValid
  responses.io.push.valid := io.mem.readDataValid && (contexts.io.pop.valid || launched)
  responses.io.push.data := io.mem.readData
  responses.io.push.context := Mux(contexts.io.pop.valid, contexts.io.pop.payload, commands.io.pop.context)

  io.bmb.rsp.valid := responses.io.pop.valid
  responses.io.pop.ready := io.bmb.rsp.ready
  io.bmb.rsp.last := True
  io.bmb.rsp.opcode := Bmb.Rsp.Opcode.SUCCESS
  io.bmb.rsp.source := 0
  io.bmb.rsp.data := responses.io.pop.data
  if (contextWidth > 0) io.bmb.rsp.context := responses.io.pop.context
  when(io.bmb.cmd.fire =/= io.bmb.rsp.fire) {
    when(io.bmb.cmd.fire) { inFlight := inFlight + 1 }
      .otherwise { inFlight := inFlight - 1 }
  }
  io.publicationBusy := inFlight =/= 0 || io.bmb.cmd.valid || commands.io.pop.valid ||
    contexts.io.pop.valid || responses.io.pop.valid || io.mem.readDataValid

  GenerationFlags.formal {
    assert(inFlight <= slots)
    when(io.mem.readDataValid) {
      assert(contexts.io.pop.valid || launched)
      assert(responses.io.push.ready)
    }
    when(io.bmb.rsp.fire) { assert(inFlight =/= 0) }
    when(io.mem.read) {
      assert(io.mem.address >= addressBase)
      assert(io.mem.address.resize(avalonAddressWidth + 1) + 4 <= addressBase + addressMask + 1)
    }
  }
}
