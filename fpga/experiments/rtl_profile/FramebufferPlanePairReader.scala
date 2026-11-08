package voodoo.framebuffer

import spinal.core._
import spinal.lib._
import spinal.lib.bus.bmb._
import voodoo._

/** Combine opposite halfwords only before the shared word read is accepted.
  * No completed or already-issued read can satisfy a later request.
  */
case class FramebufferPlanePairReader(c: Config) extends Component {
  val io = new Bundle {
    val readReq = slave(Stream(FramebufferPlaneBuffer.ReadReq(c)))
    val readRsp = master(Stream(FramebufferPlaneBuffer.ReadRsp()))
    val mem = master(Bmb(FramebufferPlaneReader.bmbParams(c)))
    val busy = out Bool ()
  }

  case class Lanes() extends Bundle {
    val firstUpper = Bool()
    val paired = Bool()
  }
  val pending = RegInit(False)
  val address = Reg(UInt(c.addressWidth.value bits))
  val firstUpper = Reg(Bool())
  val paired = RegInit(False)
  val lanes = StreamFifo(Lanes(), 8)
  val rspInput = Stream(FramebufferPlaneBuffer.ReadRsp())
  val rspQueue = rspInput.queue(2)
  val second = RegInit(False)
  val outstandingPixels = Reg(UInt(5 bits)) init (0)

  val sameWord = alignedWordAddress(io.readReq.address) === address
  val eligiblePair = pending && !paired && sameWord && (io.readReq.address(1) =/= firstUpper)
  io.mem.cmd.valid := pending && lanes.io.push.ready
  io.mem.cmd.fragment.address := address
  io.mem.cmd.fragment.opcode := Bmb.Cmd.Opcode.READ
  io.mem.cmd.fragment.length := 3
  io.mem.cmd.fragment.source := 0
  io.mem.cmd.fragment.data := 0
  io.mem.cmd.fragment.mask := 0
  io.mem.cmd.last := True

  io.readReq.ready := !pending || eligiblePair || io.mem.cmd.fire
  val merge = io.readReq.fire && eligiblePair
  lanes.io.push.valid := io.mem.cmd.fire
  lanes.io.push.firstUpper := firstUpper
  lanes.io.push.paired := paired || merge

  when(io.mem.cmd.fire) { pending := False }
  when(io.readReq.fire) {
    when(eligiblePair) {
      when(!io.mem.cmd.fire) { paired := True }
    }.otherwise {
      pending := True
      address := alignedWordAddress(io.readReq.address)
      firstUpper := io.readReq.address(1)
      paired := False
    }
  }

  val upper = lanes.io.pop.firstUpper ^ second
  rspInput.valid := io.mem.rsp.valid && lanes.io.pop.valid
  rspInput.data := upper ? io.mem.rsp.fragment.data(31 downto 16) | io.mem.rsp.fragment.data(15 downto 0)
  // Retain the same word response until both accepted halfwords are delivered.
  io.mem.rsp.ready := rspInput.ready && lanes.io.pop.valid && (!lanes.io.pop.paired || second)
  lanes.io.pop.ready := io.mem.rsp.fire
  when(rspInput.fire) { second := lanes.io.pop.paired && !second }
  io.readRsp << rspQueue
  // FIFO output-valid can briefly be low while a newly enqueued response is
  // being prefetched. Count accepted pixels through final consumer acceptance.
  when(io.readReq.fire && !io.readRsp.fire) {
    outstandingPixels := outstandingPixels + 1
  }.elsewhen(!io.readReq.fire && io.readRsp.fire) {
    outstandingPixels := outstandingPixels - 1
  }
  io.busy := outstandingPixels =/= 0
}
