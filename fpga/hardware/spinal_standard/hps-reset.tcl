# Root-operated recovery through the existing Standard GHRD RST source.
# Default is inspection only. --warm explicitly requests an HPS warm reset.
# Do not run concurrently with FPGA programming or another JTAG application.
load_package jtag
load_package insystem_source_probe
set argsList {}
if {[info exists quartus(args)]} {
    set argsList $quartus(args)
} elseif {[info exists argv]} {
    set argsList $argv
}
set warm 0
if {[llength $argsList] == 1 && [lindex $argsList 0] eq "--warm"} {
    set warm 1
} elseif {[llength $argsList] != 0} {
    error "Usage: quartus_stp -t hps-reset.tcl ?--warm?"
}
set hardware {DE-SoC [USB-1]}
if {[lsearch -exact [get_hardware_names] $hardware] < 0} {
    error "Expected DE-SoC USB-1 cable not found"
}
set candidates {}
foreach device [get_device_names -hardware_name $hardware] {
    if {[regexp -nocase {^@2:.*\(0x02d020dd\)} $device]} {
        lappend candidates $device
    }
}
if {[llength $candidates] != 1} { error "Expected exactly one reviewed FPGA at JTAG position 2" }
set device [lindex $candidates 0]
set resetInstances {}
foreach inst [get_insystem_source_probe_instance_info -hardware_name $hardware -device_name $device] {
    puts "INSTANCE=$inst"
    if {[lindex $inst 1] == 3 && [lindex $inst 2] == 0 && [lindex $inst 3] eq "RST"} {
        lappend resetInstances [lindex $inst 0]
    }
}
if {[llength $resetInstances] != 1} { error "Expected one RST instance, source width 3, probe width 0" }
set index [lindex $resetInstances 0]
start_insystem_source_probe -hardware_name $hardware -device_name $device
set raised 0
set failure [catch {
    set initial [read_source_data -instance_index $index]
    puts "RST_INITIAL=$initial"
    if {$warm} {
        if {![regexp {^0+$} $initial]} { error "RST source must initially be zero; refusing to alter other reset requests" }
        write_source_data -instance_index $index -value 000
        after 10
        puts "REQUESTING_HPS_WARM_RESET"
        write_source_data -instance_index $index -value 010
        set raised 1
        after 10
        write_source_data -instance_index $index -value 000
        set raised 0
        puts "RST_FINAL=[read_source_data -instance_index $index]"
    } else {
        puts "INSPECTION_ONLY_NO_RESET_REQUESTED"
    }
} message options]
if {$raised} { catch {write_source_data -instance_index $index -value 000} }
end_insystem_source_probe
if {$failure} { return -options $options $message }
