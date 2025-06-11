import React, { PropsWithChildren } from "react";
import {UserProfile} from "@clerk/clerk-react"


export interface UserProfilePageProps {
  children: React.ReactNode;
  label: string;
  url: string;
  labelIcon: React.ReactNode;
}

const UserProfilePage: React.FC<PropsWithChildren<UserProfilePageProps>> = ({ children, label, labelIcon, url, ...others }) => {
    return (
      <UserProfile.Page label={label} labelIcon={labelIcon} url={url}>
        {children}
      </UserProfile.Page>
    );
  };

export default UserProfilePage;

