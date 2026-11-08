package voodoo.de10

import spinal.core._
import voodoo.{Config, GenSupport}

object SpinalStandardGen extends App {
  val output = sys.env.getOrElse("SPINAL_STANDARD_RTL", "hardware/spinal_standard/rtl")
  // One TMU, direct framebuffer readers for correctness/coherency, buffered
  // writes with explicit flush, no physical display dependency.
  val config = Config.voodoo1().copy(
    maxFbDims = (640, 480),
    useFbWriteBuffer = true,
    fbWriteBufferLineWords = 64,
    useFbReadCache = false
  )
  GenSupport.de10Verilog(output).generate(
    CoreDe10(config, headless = true).setDefinitionName("SpinalStandardCore")
  )
  GenSupport.mirrorRomSidecars(output, "SpinalStandardCore")
}
