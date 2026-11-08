// Buffered board backend emits single-beat writes on this shared master.
// After flush/drain, serialize a read behind the final write on that SAME
// Avalon master and verify its enabled bytes. This is not an arbitrary timer.
module avalon_frame_fence #(
    parameter FB_BASE=32'h3f400000,
    parameter TIMEOUT_CYCLES=250000000
)(
    input wire clk, reset_n, request, quiescent,
    output wire busy,
    output reg done, error,
    input wire [31:0] s_address, s_writedata,
    input wire [10:0] s_burstcount,
    input wire [3:0] s_byteenable,
    input wire s_read, s_write,
    output wire s_waitrequest,
    output wire [31:0] s_readdata,
    output wire s_readdatavalid,
    output wire [31:0] m_address, m_writedata,
    output wire [10:0] m_burstcount,
    output wire [3:0] m_byteenable,
    output wire m_read, m_write,
    input wire m_waitrequest,
    input wire [31:0] m_readdata,
    input wire m_readdatavalid
);
    localparam PASS=0, ISSUE=1, RESPONSE=2, COMPLETE=3;
    reg [1:0] state;
    reg [31:0] last_address, last_data, timeout;
    reg [3:0] last_mask;
    reg dirty;
    wire passing=state==PASS;
    // COMPLETE only holds the request acknowledgement; the read has drained.
    assign busy=dirty || state==ISSUE || state==RESPONSE;
    wire [31:0] compare_mask={{8{last_mask[3]}},{8{last_mask[2]}},
                             {8{last_mask[1]}},{8{last_mask[0]}}};
    assign m_address=passing ? s_address : last_address;
    assign m_writedata=passing ? s_writedata : 32'd0;
    assign m_burstcount=passing ? s_burstcount : 11'd1;
    assign m_byteenable=passing ? s_byteenable : 4'hf;
    assign m_read=passing ? s_read : state==ISSUE;
    assign m_write=passing && s_write;
    assign s_waitrequest=passing ? m_waitrequest : 1'b1;
    assign s_readdata=m_readdata;
    assign s_readdatavalid=passing && m_readdatavalid;
    always @(posedge clk) begin
        if(!reset_n) begin
            state<=PASS; done<=0; error<=0; last_address<=FB_BASE;
            last_data<=0; last_mask<=0; timeout<=0; dirty<=0;
        end else begin
            done<=0;
            if(passing && s_write && !m_waitrequest) begin
                last_address<=s_address; last_data<=s_writedata; last_mask<=s_byteenable;
                dirty<=1;
                if(s_burstcount!=1) error<=1;
            end
            case(state)
                PASS: if((request || (dirty && quiescent)) && !s_read && !s_write) begin
                    state<=ISSUE; timeout<=0;
                end
                ISSUE,RESPONSE: begin
                    timeout<=timeout+1;
                    if(timeout>=TIMEOUT_CYCLES-1) begin error<=1; state<=COMPLETE; end
                    else if(m_readdatavalid && (state==RESPONSE || !m_waitrequest)) begin
                        if((m_readdata & compare_mask)!=(last_data & compare_mask)) error<=1;
                        done<=1; dirty<=0; state<=COMPLETE;
                    end else if(state==ISSUE && !m_waitrequest) state<=RESPONSE;
                end
                COMPLETE: if(!request) state<=PASS;
            endcase
        end
    end
endmodule
