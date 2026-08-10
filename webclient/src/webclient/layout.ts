export interface MapLayout {
    leftWidth: string;
    rightHidden: boolean;
    dividerHidden: boolean;
}

export function mapLayout(enabled: boolean, savedPosition: string): MapLayout {
    if (!enabled) return { leftWidth: '100%', rightHidden: true, dividerHidden: true };
    const percentage = Number.parseFloat(savedPosition);
    const width = Number.isFinite(percentage) && percentage > 5 && percentage < 95 ? `${percentage}%` : '50%';
    return { leftWidth: width, rightHidden: false, dividerHidden: false };
}
