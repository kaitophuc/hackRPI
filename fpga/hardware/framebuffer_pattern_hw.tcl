package require -exact qsys 13.1
set_module_property NAME framebuffer_pattern
set_module_property VERSION 1.0
set_module_property GROUP "GPU Platform"
set_module_property DISPLAY_NAME "Locked RGB565 framebuffer diagnostic"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
foreach {parameter default} {WIDTH 320 HEIGHT 240 CLOCK_HZ 50000000} {
    add_parameter $parameter INTEGER $default
    set_parameter_property $parameter HDL_PARAMETER true
}
set_parameter_property WIDTH ALLOWED_RANGES 2:640
set_parameter_property HEIGHT ALLOWED_RANGES 1:480
# This diagnostic integration has a fixed 50 MHz physical clock.
set_parameter_property CLOCK_HZ ALLOWED_RANGES {50000000}
set_module_property VALIDATION_CALLBACK validate_geometry
proc validate_geometry {} {
    set width [get_parameter_value WIDTH]
    set height [get_parameter_value HEIGHT]
    if {$width % 2 != 0 || $width*$height*2 + 4096 > 262144} {
        send_message error "WIDTH must be even and RGB565 framebuffer plus 4096-byte registers must fit the 256 KiB aperture"
    }
}
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH
set_fileset_property QUARTUS_SYNTH TOP_LEVEL framebuffer_pattern
add_fileset_file rtl/framebuffer_pattern.v VERILOG PATH rtl/framebuffer_pattern.v TOP_LEVEL_FILE
add_interface clock clock end
add_interface_port clock clk clk Input 1
add_interface reset reset end
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges DEASSERT
add_interface_port reset reset_n reset_n Input 1
add_interface control avalon end
set_interface_property control associatedClock clock
set_interface_property control associatedReset reset
set_interface_property control addressUnits SYMBOLS
set_interface_property control bitsPerSymbol 8
set_interface_property control maximumPendingReadTransactions 1
set_interface_property control readLatency 0
set_interface_property control explicitAddressSpan 262144
add_interface_port control address address Input 18
add_interface_port control read read Input 1
add_interface_port control write write Input 1
add_interface_port control writedata writedata Input 32
add_interface_port control byteenable byteenable Input 4
add_interface_port control readdata readdata Output 32
add_interface_port control readdatavalid readdatavalid Output 1
add_interface_port control waitrequest waitrequest Output 1

