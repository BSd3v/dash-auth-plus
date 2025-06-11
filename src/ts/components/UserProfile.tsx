import React, { PropsWithChildren } from "react";
import { UserProfile as ClerkUserProfile } from "@clerk/clerk-react";
import { resolveChildProps, newRenderDashComponent } from "../utils";

interface CustomPageProps {
    children: React.ReactNode;
    label: string;
    labelIcon?: React.ReactNode;
    url: string;
    [key: string]: any;
}

function customPage(props: CustomPageProps, index?: number) {
    const { children, label, labelIcon, url, ...otherProps } = props;
    return (
      <ClerkUserProfile.Page
        label={label}
        labelIcon={newRenderDashComponent(labelIcon)}
        url={url}
        key={index}
        {...otherProps}
      >
        {newRenderDashComponent(children)}
      </ClerkUserProfile.Page>
    );
}

interface UserProfileProps extends PropsWithChildren {}

const UserProfile: React.FC<UserProfileProps> = ({ children, ...others }) => {
    const customPages = React.Children.toArray(children).map((child, index) => {
      const childProps = resolveChildProps(child);
      return customPage(childProps as CustomPageProps, index);
    });

    return (
      <ClerkUserProfile {...others}>
        {customPages}
      </ClerkUserProfile>
    );
};

export default UserProfile;