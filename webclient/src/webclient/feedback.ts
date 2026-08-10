export function settingFeedback(setting: 'fontsize' | 'fontfamily' | 'contrast' | 'scrollback', value: string): string {
    switch (setting) {
        case 'fontsize':
            return `\r\nFont size is: ${value}.\r\n`;
        case 'fontfamily':
            return `\r\nFont changed to: ${value}.\r\n\r\nIf this looks terrible, enter :reset to go back to default font.\r\n`;
        case 'contrast':
            return `\r\nMinimum contrast ratio is: ${value}.\r\n`;
        case 'scrollback':
            return `\r\nScrollback is: ${value}.\r\n`;
    }
}

export function screenReaderFeedback(enabled: boolean): string {
    return `\r\nScreen reader mode ${enabled ? 'enabled' : 'disabled'}.\r\n`;
}
