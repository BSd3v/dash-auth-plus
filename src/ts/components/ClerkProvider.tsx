import React, { PropsWithChildren } from "react";
import { ClerkProvider as ClerkClerkProvider } from '@clerk/clerk-react'

export interface ClerkProviderProps {
    PUBLISHABLE_KEY: string;
    afterSignOutUrl?: string;
    children: React.ReactNode;
}


const ClerkProvider: React.FC<PropsWithChildren<ClerkProviderProps>> = ({ PUBLISHABLE_KEY, afterSignOutUrl, children, ...others }) => {
  return (
    <ClerkClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl={afterSignOutUrl}>
      {children}
    </ClerkClerkProvider>
  );
};

export default ClerkProvider