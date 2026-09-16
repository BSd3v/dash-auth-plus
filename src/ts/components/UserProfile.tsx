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

function customPage(props: CustomPageProps, index?: number, basePath?: any[]) {
    const { children, label, labelIcon, url, ...otherProps } = props;
    return (
      <ClerkUserProfile.Page
        label={label}
        labelIcon={newRenderDashComponent(labelIcon)}
        url={url}
        key={index}
        {...otherProps}
      >
        {newRenderDashComponent(children, index, basePath)}
      </ClerkUserProfile.Page>
    );
}

interface UserProfileProps extends PropsWithChildren {}

const UserProfile: React.FC<UserProfileProps> = ({ children, ...others }) => {
    const customPages = React.Children.toArray(children).map((child, index) => {
      const childProps = resolveChildProps(child);
      const basePath =
         React.isValidElement(child) && typeof child !== "string"
         ? child.props?.componentPath ?? []
         : [];
      return customPage(childProps as CustomPageProps, index, basePath);
    });

    return (
      <ClerkUserProfile {...others}>
        {customPages}
      </ClerkUserProfile>
    );
};

export default UserProfile;