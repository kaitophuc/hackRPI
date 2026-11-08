`timescale 1ns/1ps
module tb_publication;
  reg clk=0; always #5 clk=~clk;
  reg reset_n=0, request=0, quiescent=0;
  wire busy, done, error;
  reg [31:0] sa=0, sd=0, md=0;
  reg [10:0] sb=1;
  reg [3:0] sm=15;
  reg sr=0, sw=0, mwait=0, mvalid=0;
  wire swait, svalid, mr, mw;
  wire [31:0] sdata, ma, mdata;
  wire [10:0] mb;
  wire [3:0] mm;
  avalon_frame_fence #(.TIMEOUT_CYCLES(32)) fence(
    .clk(clk),.reset_n(reset_n),.request(request),.quiescent(quiescent),
    .busy(busy),.done(done),.error(error),
    .s_address(sa),.s_writedata(sd),.s_burstcount(sb),.s_byteenable(sm),
    .s_read(sr),.s_write(sw),.s_waitrequest(swait),.s_readdata(sdata),.s_readdatavalid(svalid),
    .m_address(ma),.m_writedata(mdata),.m_burstcount(mb),.m_byteenable(mm),
    .m_read(mr),.m_write(mw),.m_waitrequest(mwait),.m_readdata(md),.m_readdatavalid(mvalid));
  reg [11:0] ca=0;
  reg cr=0,cw=0;
  reg [31:0] cd=0;
  reg [3:0] cm=15;
  reg pipeline=0,writeback=0,active=0;
  reg link=0,manual_done=0,manual_error=0;
  wire [31:0] cdata;
  wire cvalid,cwait,flush,barrier;
  gpu2_sidecar #(.TIMEOUT_CYCLES(80)) sidecar(
    .clk(clk),.reset_n(reset_n),.address(ca),.read(cr),.write(cw),
    .writedata(cd),.byteenable(cm),.readdata(cdata),.readdatavalid(cvalid),.waitrequest(cwait),
    .pipeline_busy(pipeline),.writeback_busy(writeback | (link && busy)),
    .memory_active(active | (link && (mr || mw))),.flush(flush),.barrier_request(barrier),
    .barrier_done(link ? done : manual_done),.barrier_error(link ? error : manual_error));
  // In integrated mode, request is driven on falling edges to avoid races.
  always @(negedge clk) if(link) request=barrier;
  task tick; begin @(posedge clk); #1; end endtask
  task reset;
    begin
      @(negedge clk); reset_n=0; request=0; quiescent=0;
      sr=0;sw=0;mwait=0;mvalid=0;sb=1;sm=15;
      ca=0;cr=0;cw=0;cm=15;pipeline=0;writeback=0;active=0;
      link=0;manual_done=0;manual_error=0;
      repeat(3) tick(); @(negedge clk);reset_n=1;tick();
    end
  endtask
  task command(input [31:0] value);
    begin @(negedge clk);ca=12'hc;cd=value;cw=1;tick();@(negedge clk);cw=0; end
  endtask
  task readreg(input [11:0] addr, output [31:0] value);
    begin @(negedge clk);ca=addr;cr=1;tick();
      if(!cvalid) $fatal(1,"missing sidecar read valid");
      value=cdata;@(negedge clk);cr=0;
    end
  endtask
  task write_word(input [31:0] addr,input [31:0] data,input [3:0] mask);
    begin @(negedge clk);sa=addr;sd=data;sm=mask;sw=1;
      tick();if(!mw || swait) $fatal(1,"write not passed through");
      @(negedge clk);sw=0;tick();if(!busy) $fatal(1,"accepted write not tracked");
    end
  endtask
  task wait_read;
    integer n;
    begin n=0;while(!mr && n<20) begin tick();n=n+1;end
      if(!mr) $fatal(1,"barrier read did not issue");
    end
  endtask
  task respond(input [31:0] data);
    begin @(negedge clk);md=data;mvalid=1;tick();
      if(!done) $fatal(1,"response did not complete fence");
      if(svalid) $fatal(1,"fence response leaked to renderer");
      @(negedge clk);mvalid=0;
    end
  endtask
  reg [31:0] value;
  integer n;
  initial begin
    reset();
    // Automatic fence, final enabled bytes only, and stalled request stability.
    write_word(32'h3f400044,32'hdeadbeef,4'b0101);
    repeat(4) tick();if(mr) $fatal(1,"auto read before quiescence");
    @(negedge clk);mwait=1;quiescent=1;wait_read();
    repeat(5) begin tick();
      if(!mr || ma!=32'h3f400044 || mb!=1 || mm!=15 || mw || !swait)
        $fatal(1,"stalled barrier request changed");
    end
    @(negedge clk);mwait=0;tick();
    repeat(4) begin tick();if(done || !busy || mr) $fatal(1,"fence did not wait for delayed response");end
    respond(32'h11ad22ef); // disabled lanes intentionally differ
    if(error) $fatal(1,"disabled bytes incorrectly compared");
    repeat(3) tick();if(busy) $fatal(1,"automatic fence did not return idle");
    $display("PASS automatic fence: masks, request stalls, delayed response");
    // Explicit request with response in the acceptance cycle.
    reset();write_word(32'h3f400080,32'h12345678,15);
    @(negedge clk);request=1;wait_read();respond(32'h12345678);
    if(error) $fatal(1,"same-cycle response comparison failed");
    repeat(3) tick();
    if(busy || !swait || mr || mw) $fatal(1,"completed fence must hold handshake without claiming memory work");
    @(negedge clk);request=0;repeat(3) tick();if(busy) $fatal(1,"explicit fence did not release");
    $display("PASS explicit fence: immediate response and request hold/release");
    reset();write_word(32'h3f400000,32'h12345678,15);
    @(negedge clk);request=1;wait_read();respond(32'h12345679);
    if(!error) $fatal(1,"enabled-byte mismatch not detected");
    $display("PASS fence mismatch detection");
    reset();sb=2;write_word(32'h3f400000,32'h12345678,15);
    if(!error) $fatal(1,"unsupported write burst silently accepted");
    $display("PASS unsupported write burst detection");
    reset();@(negedge clk);request=1;mwait=1;wait_read();
    repeat(35) tick();if(!error || done) $fatal(1,"stalled-request timeout failed");
    $display("PASS fence timeout without false completion");
    reset();readreg(0,value);if(value!=32'h47505532) $fatal(1,"ID mismatch");
    command(4);@(negedge clk);pipeline=1;writeback=1;command(1);
    repeat(12) begin tick();if(barrier) $fatal(1,"barrier issued while writers busy");end
    @(negedge clk);pipeline=0;writeback=0;active=1;
    repeat(10) begin tick();if(barrier) $fatal(1,"barrier issued while memory active");end
    @(negedge clk);active=0;
    n=0;while(!barrier && n<15) begin tick();n=n+1;end
    if(!barrier || !flush) $fatal(1,"drain never reached barrier");
    readreg(8,value);if(value[2]) $fatal(1,"ready before barrier response");
    @(negedge clk);manual_done=1;tick();@(negedge clk);manual_done=0;
    readreg(8,value);if(value!=4) $fatal(1,"sidecar did not publish ready: %h",value);
    readreg(32'h20,value);if(value!=1) $fatal(1,"sequence did not increment exactly once");
    command(2);readreg(8,value);if(value!=0 || flush) $fatal(1,"release did not return idle");
    $display("PASS sidecar drain, barrier, ready, sequence, release");
    reset();command(1);repeat(85) tick();readreg(8,value);
    if(!value[3] || value[2]) $fatal(1,"sidecar timeout published frame");
    readreg(32'h20,value);if(value!=0) $fatal(1,"failed frame incremented sequence");
    $display("PASS sidecar timeout refuses publication");
    reset();command(1);repeat(12) tick();@(negedge clk);manual_error=1;tick();
    readreg(8,value);if(!value[3] || value[2]) $fatal(1,"sidecar accepted barrier error");
    $display("PASS sidecar barrier error refuses publication");
    reset();command(1);repeat(12) tick();
    @(negedge clk);manual_done=1;writeback=1;tick();
    readreg(8,value);if(!value[3] || value[2]) $fatal(1,"sidecar accepted completion with outstanding writer");
    $display("PASS sidecar rejects completion with outstanding writer");
    reset();cm=3;command(1);readreg(8,value);
    if(!value[3] || value[2] || flush) $fatal(1,"partial command byte enable accepted");
    $display("PASS sidecar rejects partial command write");
    // Exact current wrapper busy wiring, to expose handshake circularity.
    reset();link=1;quiescent=1;command(4);command(1);wait_read();respond(0);
    repeat(3) tick();readreg(8,value);
    if(value!=4) $fatal(1,"integrated explicit fence failed to publish ready: status=%h",value);
    $display("PASS integrated sidecar/fence publication");
    $finish;
  end
  initial begin #100000;$fatal(1,"testbench timeout");end
endmodule
