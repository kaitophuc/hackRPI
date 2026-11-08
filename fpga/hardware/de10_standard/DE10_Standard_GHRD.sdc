# Active FPGA domain for LAN-only bring-up; HPS constraints from soc_system.qip.
create_clock -name CLOCK_50 -period 20.000 [get_ports CLOCK_50]
create_clock -name altera_reserved_tck -period 40.000 [get_ports altera_reserved_tck]
set_input_delay -clock altera_reserved_tck -clock_fall 3 [get_ports altera_reserved_tdi]
set_input_delay -clock altera_reserved_tck -clock_fall 3 [get_ports altera_reserved_tms]
set_output_delay -clock altera_reserved_tck 3 [get_ports altera_reserved_tdo]
derive_pll_clocks
derive_clock_uncertainty
# Human-operated switches and buttons are asynchronous diagnostic PIO inputs.
set_false_path -from [get_ports {SW[*] KEY[*]}]
