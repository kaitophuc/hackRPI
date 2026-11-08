// Original bring-up peripheral, interface documented in docs/interface.md.
module framebuffer_pattern #(
    parameter WIDTH = 320, parameter HEIGHT = 240,
    parameter CLOCK_HZ = 50000000
)(
    input wire clk, input wire reset_n,
    input wire [17:0] address, input wire read, input wire write,
    input wire [31:0] writedata, input wire [3:0] byteenable,
    output wire [31:0] readdata, output reg readdatavalid,
    output wire waitrequest
);
    localparam WORDS = (WIDTH*HEIGHT+1)/2;
    generate if (WIDTH <= 0 || WIDTH % 2 != 0 || HEIGHT <= 0 ||
                 WIDTH*HEIGHT*2 + 4096 > 262144) begin : invalid_geometry
        initial $error("WIDTH must be positive/even, HEIGHT positive, aperture <= 256KiB");
    end endgenerate
    (* ramstyle = "M10K" *) reg [31:0] framebuffer [0:WORDS-1];
    reg busy, ready;
    reg [31:0] frame_sequence, cycles, last_cycles;
    integer x, y, wr_index;
    reg [31:0] ram_read, register_read;
    reg framebuffer_read;
    wire frame_address = address >= 18'h1000 &&
                         address < 4096 + WORDS*4;
    wire [16:0] rd_index = (address - 18'h1000) >> 2;
    assign waitrequest = 1'b0;
    assign readdata = framebuffer_read ? ram_read : register_read;
    function [15:0] pixel;
        input integer px, py;
        begin pixel = ((px & 31) << 11) | ((py & 63) << 5) | ((px ^ py) & 31); end
    endfunction
    // RAM contents intentionally have no reset; unpublished contents are unreadable.
    always @(posedge clk) begin
        // Keep the RAM read port in Quartus' canonical synchronous-read form.
        // Publication/valid gating belongs in the response mux, outside RAM.
        ram_read <= framebuffer[rd_index];
        if (busy) framebuffer[wr_index] <= {pixel(x+1,y),pixel(x,y)};
    end
    always @(posedge clk) begin
        if (!reset_n) begin
            busy <= 0; ready <= 0; frame_sequence <= 0; cycles <= 0;
            last_cycles <= 0; x <= 0; y <= 0; wr_index <= 0;
            readdatavalid <= 0; framebuffer_read <= 0; register_read <= 0;
        end else begin
            readdatavalid <= read;
            framebuffer_read <= read && ready && frame_address;
            register_read <= 0;
            if (read) begin
                case(address)
                    0: register_read <= 32'h47505531;
                    4: register_read <= 1;
                    8: register_read <= {30'd0,ready,busy};
                    16: register_read <= WIDTH;
                    20: register_read <= HEIGHT;
                    24: register_read <= WIDTH*2;
                    28: register_read <= 1;
                    32: register_read <= frame_sequence;
                    36: register_read <= last_cycles;
                    40: register_read <= CLOCK_HZ;
                    default: register_read <= 0;
                endcase
            end
            if (busy) begin
                cycles <= cycles + 1;
                if (wr_index == WORDS-1) begin
                    busy <= 0; ready <= 1; frame_sequence <= frame_sequence + 1;
                    last_cycles <= cycles + 1;
                end else begin
                    wr_index <= wr_index + 1;
                    if (x == WIDTH-2) begin x <= 0; y <= y+1; end
                    else x <= x+2;
                end
            end
            if (write && address == 12 && byteenable == 4'hf) begin
                if (writedata == 1 && !busy && !ready) begin
                    busy <= 1; cycles <= 0; x <= 0; y <= 0; wr_index <= 0;
                end
                if (writedata == 2 && !busy) ready <= 0;
            end
        end
    end
endmodule

