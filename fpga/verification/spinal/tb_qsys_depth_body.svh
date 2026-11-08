integer cycle=0,sent=0,received=0,head=0,tail=0,pending_max=0;
integer due[0:255],beats,beat,lane,last_due=0;
reg [255:0] replies[0:255];
reg accepted,returned,launched;
reg [31:0] physical;
function automatic [31:0] word_data(input [31:0] address);
 word_data=address ^ 32'h13579bdf;
endfunction
function automatic [255:0] line_data(input [31:0] address);
 integer index;
 begin for(index=0;index<8;index=index+1)line_data[index*32+:32]=word_data(address+index*4);end
endfunction

initial begin
 repeat(8)@(negedge clk);reset=0;repeat(12)@(negedge clk);
 while(received<64 && cycle<10000)begin
  @(negedge clk);
  aux_read=sent<64 && sent-received<8;
  aux_write=0;aux_address=32'h3f400000+sent*4;aux_burstcount=1;aux_byteenable=15;
  mem_readdatavalid=0;
  if(head<tail && due[head]<=cycle)begin
   mem_readdatavalid=1;mem_readdata=replies[head];
  end
  // The slave grants only after seeing read, including periodic stalls.
  mem_waitrequest=1;
  #1;if(mem_read && cycle%5!=0)mem_waitrequest=0;
  #1;
  accepted=aux_read && !aux_waitrequest;
  returned=aux_readdatavalid;
  launched=mem_read && !mem_waitrequest;
  if(mem_write)$fatal(1,"unexpected DDR write during read test");
  if(returned)begin
   if(aux_readdata!==word_data(32'h3f400000+received*4))
    $fatal(1,"wrong 256-to32 lane/order at response %0d: %h",received,aux_readdata);
  end
  @(posedge clk);
  if(mem_readdatavalid)head=head+1;
  if(accepted)sent=sent+1;
  if(returned)received=received+1;
  if(launched)begin
   physical={mem_address,5'b00000};
   if(physical<32'h3f400000 || physical>=32'h3f400100)$fatal(1,"DDR address translation error %h",physical);
   beats=mem_burstcount;
   if(beats<1 || beats>8)$fatal(1,"unexpected widened burst %0d",beats);
   for(beat=0;beat<beats;beat=beat+1)begin
    if(tail>=256)$fatal(1,"response queue overflow");
    due[tail]=cycle+16+beat;
    if(due[tail]<=last_due)due[tail]=last_due+1;
    last_due=due[tail];replies[tail]=line_data(physical+32*beat);tail=tail+1;
   end
  end
  if(tail-head>pending_max)pending_max=tail-head;
  cycle=cycle+1;
 end
 if(received!=64 || sent!=64)$fatal(1,"fabric stalled: accepted=%0d responses=%0d",sent,received);
 if(pending_max<2)$fatal(1,"fabric serialized all reads; no physical overlap possible");
 $display("PASS actual Qsys 32-to256 depth fabric: %0d ordered words, max DDR response beats pending=%0d, cycles=%0d",received,pending_max,cycle);
 $finish;
end
initial begin #300000;$fatal(1,"Qsys depth fabric timeout");end
