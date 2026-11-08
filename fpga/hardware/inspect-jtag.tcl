# Read-only: enumerate debug services; no FPGA configuration or MMIO transaction.
puts "MASTER_SERVICES=[get_service_paths master]"
puts "DEVICE_SERVICES=[get_service_paths device]"
puts "SLD_SERVICES=[get_service_paths sld]"
