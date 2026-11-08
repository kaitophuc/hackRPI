package require -exact qsys 25.1
set here $standard_project_dir
# Preserve the proven Standard DDR timings, peripheral mux and physical device.
load_system [file join $here ../de10_standard/soc_system.qsys]
remove_instance framebuffer_pattern_0
add_instance spinal_gpu_0 gpu_spinal_standard 2.0
add_connection clk_0.clk spinal_gpu_0.clock
add_connection clk_0.clk_reset spinal_gpu_0.reset
add_connection hps_0.h2f_lw_axi_master spinal_gpu_0.control
set_connection_parameter_value hps_0.h2f_lw_axi_master/spinal_gpu_0.control baseAddress 0x00040000
add_connection hps_0.h2f_axi_master spinal_gpu_0.sst
set_connection_parameter_value hps_0.h2f_axi_master/spinal_gpu_0.sst baseAddress 0x00000000
# One MPFE port is required for overlapping-address ordering during LFB reads.
foreach master {fb_write fb_color_write fb_aux_write fb_color_read fb_aux_read tex} {
    add_connection spinal_gpu_0.$master hps_0.f2h_sdram0_data
    set_connection_parameter_value spinal_gpu_0.$master/hps_0.f2h_sdram0_data baseAddress 0x00000000
}
validate_system
save_system [file join $here spinal_system.qsys]
