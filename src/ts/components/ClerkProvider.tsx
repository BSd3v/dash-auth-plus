import React, { PropsWithChildren } from "react";
import { ClerkProvider as ClerkClerkProvider } from '@clerk/clerk-react'
import { dark, neobrutalism } from '@clerk/themes'

const themes = {
  'dark': dark,
  'neobrutalism': neobrutalism
};

export interface ClerkProviderProps {
    PUBLISHABLE_KEY: string;
    afterSignOutUrl?: string;
    children: React.ReactNode;
    themeName?: string;
    id?: string;
    [key: string]: any;
}


const ClerkProvider: React.FC<PropsWithChildren<ClerkProviderProps>> = ({
  PUBLISHABLE_KEY,
  afterSignOutUrl,
  children,
  themeName,
  ...others
}) => {

  const appearance = React.useMemo(() => {
      const theme = themeName ? themes[themeName as keyof typeof themes] : undefined;
      return theme ? { baseTheme: theme } : undefined;
    }, [themeName]);

    return (
      <ClerkClerkProvider
        publishableKey={PUBLISHABLE_KEY}
        afterSignOutUrl={afterSignOutUrl}
        appearance={appearance}
        {...others}
      >
        {children}
      </ClerkClerkProvider>
    );
};

export default ClerkProvider