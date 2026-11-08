// GPU2 ABI: explicit buffered-write flush, drain and same-master read barrier.
// No ready publication is permitted solely because the pixel pipeline is idle.
module gpu2_sidecar #(
    parameter CLOCK_HZ=50000000,
    parameter TIMEOUT_CYCLES=250000000
)(
    input wire clk, reset_n,
    input wire [11:0] address,
    input wire read, write,
    input wire [31:0] writedata,
    input wire [3:0] byteenable,
    output reg [31:0] readdata,
    output reg readdatavalid,
    output wire waitrequest,
    input wire pipeline_busy, writeback_busy, memory_active,
    output wire flush,
    output wire barrier_request,
    input wire barrier_done, barrier_error
);
    localparam IDLE=0, DRAIN=1, BARRIER=2, READY=3, FAILED=4;
    reg [2:0] state;
    reg sticky_error, timing_active;
    reg [3:0] quiet_cycles;
    reg [31:0] deadline, frame_sequence, cycles, busy_cycles;
    reg [31:0] last_cycles, last_busy_cycles;
    assign waitrequest=1'b0;
    assign flush=state==DRAIN || state==BARRIER || state==READY || state==FAILED;
    assign barrier_request=state==BARRIER;
    always @(posedge clk) begin
        if(!reset_n) begin
            state<=IDLE; sticky_error<=0; timing_active<=0; quiet_cycles<=0;
            deadline<=0; frame_sequence<=0; cycles<=0; busy_cycles<=0;
            last_cycles<=0; last_busy_cycles<=0; readdata<=0; readdatavalid<=0;
        end else begin
            readdatavalid<=read;
            readdata<=0;
            if(read) case(address)
                12'h000: readdata<=32'h47505532;
                12'h004: readdata<=2;
                12'h008: readdata<={28'd0,sticky_error,state==READY,
                                   state==DRAIN || state==BARRIER,pipeline_busy};
                12'h010: readdata<=320;
                12'h014: readdata<=240;
                12'h018: readdata<=640;
                12'h01c: readdata<=1;
                12'h020: readdata<=frame_sequence;
                12'h024: readdata<=last_cycles;
                12'h028: readdata<=CLOCK_HZ;
                12'h02c: readdata<=last_busy_cycles;
                default: readdata<=0;
            endcase
            if(timing_active) begin
                cycles<=cycles+1;
                if(pipeline_busy) busy_cycles<=busy_cycles+1;
            end
            if(state==DRAIN || state==BARRIER) begin
                deadline<=deadline+1;
                if(deadline>=TIMEOUT_CYCLES-1 || barrier_error) begin
                    state<=FAILED; sticky_error<=1; timing_active<=0;
                end else if(state==DRAIN) begin
                    if(pipeline_busy || writeback_busy || memory_active) quiet_cycles<=0;
                    else if(quiet_cycles==7) begin state<=BARRIER; quiet_cycles<=0; end
                    else quiet_cycles<=quiet_cycles+1;
                end else if(barrier_done) begin
                    if(pipeline_busy || writeback_busy || memory_active) begin
                        state<=FAILED; sticky_error<=1; timing_active<=0;
                    end else begin
                        state<=READY; frame_sequence<=frame_sequence+1;
                        last_cycles<=cycles+1;
                        last_busy_cycles<=busy_cycles;
                        timing_active<=0;
                    end
                end
            end
            if(write && address==12'h00c) begin
                if(byteenable!=4'hf) sticky_error<=1;
                else case(writedata)
                    1: if(state==IDLE && !sticky_error) begin
                        state<=DRAIN; deadline<=0; quiet_cycles<=0;
                    end else sticky_error<=1;
                    2: if(state==READY) state<=IDLE;
                       else sticky_error<=1;
                    4: if(state==IDLE && !timing_active && !sticky_error) begin
                        timing_active<=1; cycles<=0; busy_cycles<=0;
                    end else sticky_error<=1;
                    default: sticky_error<=1;
                endcase
            end
        end
    end
endmodule
