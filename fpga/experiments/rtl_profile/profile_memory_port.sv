// Deterministic, in-order, pipelined Avalon slave. Responses may have a
// configurable latency; accepted requests do not wait for earlier responses.
module profile_memory_port(
 input wire clk, reset,
 input wire [31:0] latency, stall_period,
 input wire read, write,
 output wire waitn,
 input wire [31:0] address, data,
 input wire [10:0] burst,
 input wire [3:0] mask,
 output reg valid=0,
 output reg [31:0] q=0
);
 integer tick=0, head=0, tail=0, index, lane, beat, due, last_due=0;
 integer pending_due[0:8191];
 reg [31:0] pending_data[0:8191];
 integer reads=0, writes=0, blocked=0, responses=0, max_pending=0;
 assign waitn = stall_period < 2 ? 1'b1 : tick % stall_period != stall_period-1;
 always @(posedge clk) begin
  if(reset) begin tick=0; head=0; tail=0; valid<=0; last_due=0; end
  else begin
   tick=tick+1; valid<=0;
   if((read || write) && !waitn) blocked=blocked+1;
   if(read && write) $fatal(1,"simultaneous Avalon read/write");
   if((read || write) && waitn) begin
    if(address < 32'h3f400000 || address >= 32'h40000000 || address[1:0]!=0)
     $fatal(1,"invalid GPU memory address %h",address);
    index=(address-32'h3f400000)>>2;
    if(write) begin
     if(burst!=1) $fatal(1,"board writer must issue single beats");
     for(lane=0;lane<4;lane=lane+1) if(mask[lane])
      tb_core_profile.memory[index][lane*8+:8]=data[lane*8+:8];
     writes=writes+1;
    end
    if(read) begin
     if(burst<1 || burst>1024) $fatal(1,"invalid memory burst");
     for(beat=0;beat<burst;beat=beat+1) begin
      if(tail-head>=8192 || index+beat>=3145728) $fatal(1,"RAM model queue/range overflow");
      due=tick+latency+beat;
      if(due<=last_due) due=last_due+1;
      pending_due[tail%8192]=due;
      pending_data[tail%8192]=tb_core_profile.memory[index+beat];
      last_due=due; tail=tail+1;
     end
     reads=reads+1;
    end
   end
   if(head<tail && pending_due[head%8192]<=tick) begin
    valid<=1; q<=pending_data[head%8192]; head=head+1; responses=responses+1;
   end
   if(tail-head>max_pending) max_pending=tail-head;
  end
 end
endmodule
