wire cpu_cmd_valid;
H2fLwToBmbBridge frontend(
 .clk(clk), .reset(reset),
 .io_h2fLw_address(address), .io_h2fLw_read(read), .io_h2fLw_write(write),
 .io_h2fLw_byteenable(byteenable), .io_h2fLw_writedata(writedata),
 .io_h2fLw_waitrequest(waitrequest), .io_h2fLw_readdata(readdata),
 .io_h2fLw_readdatavalid(readdatavalid),
 .io_cpuBus_cmd_valid(cpu_cmd_valid), .io_cpuBus_cmd_ready(1'b0),
 .io_cpuBus_rsp_valid(1'b0), .io_cpuBus_rsp_payload_last(1'b1),
 .io_cpuBus_rsp_payload_fragment_source(4'b0),
 .io_cpuBus_rsp_payload_fragment_opcode(1'b0),
 .io_cpuBus_rsp_payload_fragment_data(32'b0)
);
integer accepted=0, returned=0;
always @(posedge clk) if(!reset) begin
 if(read && !waitrequest) begin
   accepted=accepted+1;
   $display("AVALON read word=%h mask=%h cycle=%0t",address,byteenable,$time);
 end
 if(readdatavalid) returned=returned+1;
 if(cpu_cmd_valid) $fatal(1,"local debug reads reached BMB renderer");
end

task automatic axi_read(input [29:0] addr, input [2:0] size, input integer beats);
 integer n, timeout_count;
 reg [63:0] held;
 reg [31:0] lane;
 begin
  @(negedge clk); araddr=addr; arsize=size; arlen=beats-1; arvalid=1;
  timeout_count=0;
  @(posedge clk);
  while(!arready && timeout_count<100) begin @(posedge clk); timeout_count=timeout_count+1; end
  if(!arready) $fatal(1,"AXI read address not accepted");
  @(negedge clk); arvalid=0;
  for(n=0;n<beats;n=n+1) begin
   timeout_count=0;
   while(!rvalid && timeout_count<200) begin @(negedge clk); timeout_count=timeout_count+1; end
   if(!rvalid) $fatal(1,"AXI read response missing addr=%h beat=%0d",addr,n);
   if(rresp!=0 || rid!=12'h123 || rlast!=(n==beats-1)) $fatal(1,"bad AXI metadata");
   held=rdata;
   if(addr==30'h254 && rdata[63:32]!=0) $fatal(1,"initial status is nonzero");
   if(addr==30'h258 && n==0) begin
    if((rdata[31:0] & 32'h14)!=32'h14) $fatal(1,"debug read decode/address failed");
   end
   repeat(3) begin
    @(negedge clk);
    if(!rvalid || rdata!==held) $fatal(1,"AXI response changed under backpressure");
   end
   rready=1;
   @(posedge clk); @(negedge clk); rready=0;
  end
  repeat(3) @(negedge clk);
 end
endtask

initial begin
 awid=0;awaddr=0;awlen=0;awsize=2;awburst=1;awlock=0;awcache=0;awprot=0;awvalid=0;
 wid=0;wdata=0;wstrb=0;wlast=0;wvalid=0;bready=1;
 arid=12'h123;araddr=0;arlen=0;arsize=2;arburst=1;arlock=0;arcache=0;arprot=0;arvalid=0;rready=0;
 repeat(8) @(negedge clk); reset=0; repeat(8) @(negedge clk);
 // Actual native first read: one 32-bit word in the high half of the 64-bit bus.
 axi_read(30'h254,3'd2,1);
 axi_read(30'h258,3'd2,4);
 // One wide beat requires two serial 32-bit Avalon responses.
 axi_read(30'h258,3'd3,1);
 if(accepted!=7 || returned!=7) $fatal(1,"wrong Avalon request/response totals %0d %0d",accepted,returned);
 $display("PASS actual generated Qsys64-to32 fabric and frontend: seven local reads, AXI response stalls");
 $finish;
end
initial begin #100000; $fatal(1,"Qsys SST simulation timeout"); end
