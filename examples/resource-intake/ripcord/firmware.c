/* Self-authored LM3S6965 (Cortex-M3) fixture: UART0 banner plus a checksum line. */
#include <stdint.h>

#define SYSCTL_RCGC1 (*(volatile uint32_t *)0x400FE104u)
#define UART0_DR     (*(volatile uint32_t *)0x4000C000u)
#define UART0_FR     (*(volatile uint32_t *)0x4000C018u)
#define UART0_CTL    (*(volatile uint32_t *)0x4000C030u)

extern uint32_t _estack;
void reset_handler(void);
void default_handler(void);

__attribute__((section(".vectors"), used))
const void *const vectors[16] = {
    &_estack, reset_handler, default_handler, default_handler,
    default_handler, default_handler, default_handler, 0, 0, 0, 0,
    default_handler, default_handler, 0, default_handler, default_handler,
};

static const char banner[] = "RIPCORD-FIXTURE\n";

__attribute__((noinline)) void uart_init(void) {
    SYSCTL_RCGC1 |= 1u;
    UART0_CTL = 0x301u;
}

__attribute__((noinline)) void uart_putc(char c) {
    while (UART0_FR & (1u << 5)) {
    }
    UART0_DR = (uint32_t)c;
}

__attribute__((noinline)) void uart_puts(const char *s) {
    while (*s) {
        uart_putc(*s++);
    }
}

__attribute__((noinline)) uint32_t fixture_checksum(const char *s) {
    uint32_t total = 0;
    while (*s) {
        total = (total * 31u + (uint8_t)*s++) & 0xFFFFu;
    }
    return total;
}

__attribute__((noinline)) void uart_puthex16(uint32_t value) {
    for (int shift = 12; shift >= 0; shift -= 4) {
        uint32_t nibble = (value >> shift) & 0xFu;
        uart_putc((char)(nibble < 10u ? '0' + nibble : 'A' + nibble - 10u));
    }
    uart_putc('\n');
}

void default_handler(void) {
    for (;;) {
    }
}

void reset_handler(void) {
    uart_init();
    uart_puts(banner);
    uart_puthex16(fixture_checksum(banner));
    for (;;) {
    }
}
