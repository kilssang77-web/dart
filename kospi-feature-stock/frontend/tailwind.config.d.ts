declare const _default: {
    content: string[];
    darkMode: "class";
    theme: {
        extend: {
            colors: {
                dark: {
                    bg: string;
                    card: string;
                    border: string;
                    muted: string;
                    fg: string;
                };
                light: {
                    bg: string;
                    card: string;
                    border: string;
                    muted: string;
                    fg: string;
                };
                brand: {
                    cyan: string;
                    green: string;
                    red: string;
                    yellow: string;
                    blue: string;
                    purple: string;
                };
                hts: {
                    up: string;
                    dn: string;
                    flat: string;
                };
            };
            fontFamily: {
                mono: [string, string, string, string];
                sans: [string, string, string, string, string];
            };
            animation: {
                blink: string;
                spin: string;
                toastIn: string;
                flashUp: string;
                flashDn: string;
                fadeHighlight: string;
            };
            keyframes: {
                blink: {
                    '0%,100%': {
                        opacity: string;
                    };
                    '50%': {
                        opacity: string;
                    };
                };
                toastIn: {
                    from: {
                        transform: string;
                        opacity: string;
                    };
                    to: {
                        transform: string;
                        opacity: string;
                    };
                };
                flashUp: {
                    '0%': {
                        background: string;
                    };
                    '100%': {
                        background: string;
                    };
                };
                flashDn: {
                    '0%': {
                        background: string;
                    };
                    '100%': {
                        background: string;
                    };
                };
                fadeHighlight: {
                    from: {
                        background: string;
                    };
                    to: {
                        background: string;
                    };
                };
            };
        };
    };
    plugins: any[];
};
export default _default;
