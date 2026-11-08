reg [31:0] memory[0:3145727]; // Shared 4 MB framebuffer + 8 MB texture pool.
integer memory_latency=16, stall_period=0, mode=1, width=64, height=32, pairs=2, pattern=0;
integer cycles=0, i, pair, quiet, elapsed, fd, lane, changed, back_changed;
integer cpu_wait=0, fifo_sync_wait=0, setup_wait=0, setup_active=0;
integer raster_wait=0, span_active=0, tex_wait=0, tex_rsp_wait=0;
integer fb_input_wait=0, depth_req_wait=0, depth_rsp_wait=0, color_rsp_wait=0;
integer color_write_wait=0, aux_write_wait=0, pixels=0;
integer depth_memory_wait=0, color_memory_wait=0, texture_memory_wait=0;
reg measuring=0;
`define PIPE dut.core_1.pixelPipeline_1
`define FIFO dut.core_1.pciFifo_1
always @(posedge clk) if(!reset && measuring) begin
 cycles=cycles+1;
 if(io_h2fLw_write && io_h2fLw_waitrequest)cpu_wait=cpu_wait+1;
 if(`FIFO.drainControl_issuedWrite_valid && `FIFO.issuedSyncBlocked)fifo_sync_wait=fifo_sync_wait+1;
 if(`PIPE.triangleSetup_1.i_valid && !`PIPE.triangleSetup_1.i_ready)setup_wait=setup_wait+1;
 if(`PIPE.triangleSetup_1.i_valid || `PIPE.triangleSetup_1.o_valid)setup_active=setup_active+1;
 if(`PIPE.rasterizer_1.o_valid && !`PIPE.rasterizer_1.o_ready)raster_wait=raster_wait+1;
 if(`PIPE.rasterizer_1.spanWalker_1.running)span_active=span_active+1;
 if(`PIPE.tmu_1.io_input_valid && !`PIPE.tmu_1.io_input_ready)tex_wait=tex_wait+1;
 if(`PIPE.tmu_1.io_texRead_cmd_valid && !`PIPE.tmu_1.io_texRead_cmd_ready)tex_rsp_wait=tex_rsp_wait+1;
 if(`PIPE.fbAccess.io_input_valid && !`PIPE.fbAccess.io_input_ready)fb_input_wait=fb_input_wait+1;
 if(`PIPE.fbAccess.io_fbReadAuxReq_valid && !`PIPE.fbAccess.io_fbReadAuxReq_ready)depth_req_wait=depth_req_wait+1;
 if(mode!=0 && `PIPE.fbAccess.inFlightCount!=0 && `PIPE.fbAccess.io_fbReadAuxRsp_ready && !`PIPE.fbAccess.io_fbReadAuxRsp_valid)depth_rsp_wait=depth_rsp_wait+1;
 if(mode==3 && `PIPE.fbAccess.inFlightCount!=0 && `PIPE.fbAccess.io_fbReadColorRsp_ready && !`PIPE.fbAccess.io_fbReadColorRsp_valid)color_rsp_wait=color_rsp_wait+1;
 if(`PIPE.io_colorWrite_valid && !`PIPE.io_colorWrite_ready)color_write_wait=color_write_wait+1;
 if(`PIPE.io_auxWrite_valid && !`PIPE.io_auxWrite_ready)aux_write_wait=aux_write_wait+1;
 if(`PIPE.fbAccess.io_output_valid && `PIPE.fbAccess.io_output_ready)pixels=pixels+1;
 if(ramFbAuxRead.head<ramFbAuxRead.tail && !io_memFbAuxRead_readDataValid)depth_memory_wait=depth_memory_wait+1;
 if(ramFbColorRead.head<ramFbColorRead.tail && !io_memFbColorRead_readDataValid)color_memory_wait=color_memory_wait+1;
 if(ramTex.head<ramTex.tail && !io_memTex_readDataValid)texture_memory_wait=texture_memory_wait+1;
end

task automatic write_reg(input integer addr,input reg [31:0] value);
 integer waited;
 begin
  @(negedge clk); io_h2fLw_address=addr>>2;io_h2fLw_writedata=value;
  io_h2fLw_byteenable=15;io_h2fLw_write=1;
  waited=0;
  @(posedge clk);
  while(io_h2fLw_waitrequest && waited<500000)begin @(posedge clk);waited=waited+1;end
  if(waited>=500000)$fatal(1,"CPU write timed out %h",addr);
  @(negedge clk);io_h2fLw_write=0;
 end
endtask

task automatic triangle(input integer ax,ay,bx,by,cx,cy);
 begin
  write_reg('h008,ax*16);write_reg('h00c,ay*16);
  write_reg('h010,bx*16);write_reg('h014,by*16);
  write_reg('h018,cx*16);write_reg('h01c,cy*16);
  write_reg('h080,0);
  // Match the synchronization density of the selected full-game driver.
  write_reg('h120,0);write_reg('h120,0);write_reg('h120,0);
 end
endtask

initial begin
 if($value$plusargs("LATENCY=%d",memory_latency))begin end
 if($value$plusargs("STALL=%d",stall_period))begin end
 if($value$plusargs("MODE=%d",mode))begin end
 if($value$plusargs("WIDTH=%d",width))begin end
 if($value$plusargs("HEIGHT=%d",height))begin end
 if($value$plusargs("PAIRS=%d",pairs))begin end
 if($value$plusargs("PATTERN=%d",pattern))begin end
 for(i=0;i<3145728;i=i+1)memory[i]=i<1048576 ? 32'hffffffff : 32'h07e0f800;
 repeat(8)@(negedge clk);reset=0;repeat(8)@(negedge clk);
 write_reg('h214,5<<4); // 320 pixel stride.
 write_reg('h218,38<<11); // Distinct front/back/aux surfaces, 38 x 4 KB each.
 write_reg('h118,320);write_reg('h11c,240);
 write_reg('h104,mode==2 ? 32'h08000001 : 0);
 write_reg('h108,0);
 write_reg('h10c,mode==3 ? 32'h00005110 : 0); // alpha blend only in blend case.
 write_reg('h110,mode==0 ? 32'h00000201 : 32'h00000671); // LEQUAL, RGB/depth writes.
 write_reg('h020,96<<12);write_reg('h024,80<<12);write_reg('h028,48<<12);
 write_reg('h030,128<<12);write_reg('h02c,32768<<12);write_reg('h03c,32'h40000000);
 write_reg('h300,10<<8);write_reg('h304,32'h00000200);write_reg('h30c,0);
 if(mode==2)begin write_reg('h054,1<<18);write_reg('h078,1<<18);end
 write_reg('h120,0);repeat(100)@(negedge clk);
 measuring=1;
 for(pair=0;pair<pairs;pair=pair+1)begin
  if(pattern!=0)begin
   write_reg('h020,(pair%2 ? 192 : 64)<<12);
   write_reg('h024,(pair%2 ? 48 : 160)<<12);
  end
  if(pattern==1)write_reg('h02c,(pair%3==0 ? 'h6000 : pair%3==1 ? 'h2000 : 'h8000)<<12);
  if(pattern==2)write_reg('h110,(mode==0 ? 32'h00000201 : 32'h00000671) | ((pair%2)<<14));
  triangle(0,0,width,0,0,height);
  triangle(width,0,width,height,0,height);
 end
 @(negedge clk);io_fenceFlush=1;
 quiet=0;elapsed=0;
 while(quiet<16 && elapsed<500000)begin
  @(negedge clk);elapsed=elapsed+1;
  if(io_publicationPipelineBusy || io_publicationWriteBusy)quiet=0;else quiet=quiet+1;
 end
 if(elapsed>=500000)$fatal(1,"renderer failed to drain");
 measuring=0;io_fenceFlush=0;
 if(pixels==0)$fatal(1,"empty scene cannot support throughput conclusions");
 changed=0;
 for(i=0;i<320*240;i=i+1)
  if(memory[i>>1][(i%2)*16+:16]!=16'hffff)changed=changed+1;
 if(changed==0)$fatal(1,"no color pixels written");
 back_changed=0;
 if(pattern==2 && pairs>1)begin
  for(i=0;i<320*240;i=i+1)
   if(memory[38912+(i>>1)][(i%2)*16+:16]!=16'hffff)back_changed=back_changed+1;
  if(back_changed==0)$fatal(1,"alternating-buffer test never wrote the back buffer");
 end
 fd=$fopen("pixels.bin","wb");
 // Preserve all 4 MB of framebuffer memory, including masks and untouched data.
 for(i=0;i<1048576;i=i+1)for(lane=0;lane<4;lane=lane+1)$fwrite(fd,"%c",memory[i][lane*8+:8]);
 $fclose(fd);
 $display("MEMORY {\"depth_memory_response_wait\":%0d,\"color_memory_response_wait\":%0d,\"texture_memory_response_wait\":%0d,\"framebuffer_memory_accept_wait\":%0d,\"texture_memory_accept_wait\":%0d,\"depth_memory_accept_wait\":%0d}",depth_memory_wait,color_memory_wait,texture_memory_wait,ramFbWrite.blocked+ramFbColorWrite.blocked+ramFbAuxWrite.blocked,ramTex.blocked,ramFbAuxRead.blocked);
 $display("PROFILE {\"cycles\":%0d,\"cpu_wait\":%0d,\"fifo_sync_wait\":%0d,\"setup_wait\":%0d,\"setup_active\":%0d,\"raster_wait\":%0d,\"span_active\":%0d,\"texture_input_wait\":%0d,\"texture_command_wait\":%0d,\"fb_input_wait\":%0d,\"depth_request_wait\":%0d,\"depth_response_empty\":%0d,\"color_response_empty\":%0d,\"color_write_wait\":%0d,\"aux_write_wait\":%0d,\"pixels\":%0d,\"changed_color_pixels\":%0d,\"depth_reads\":%0d,\"color_reads\":%0d,\"texture_reads\":%0d,\"framebuffer_writes\":%0d,\"max_depth_pending\":%0d}",cycles,cpu_wait,fifo_sync_wait,setup_wait,setup_active,raster_wait,span_active,tex_wait,tex_rsp_wait,fb_input_wait,depth_req_wait,depth_rsp_wait,color_rsp_wait,color_write_wait,aux_write_wait,pixels,changed,ramFbAuxRead.reads,ramFbColorRead.reads,ramTex.reads,ramFbWrite.writes+ramFbColorWrite.writes+ramFbAuxWrite.writes,ramFbAuxRead.max_pending);
 $finish;
end
initial begin #20000000;$fatal(1,"full core profile timeout");end
`undef PIPE
`undef FIFO
