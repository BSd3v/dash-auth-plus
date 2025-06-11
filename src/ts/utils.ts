/**
 * Utility functions to support both Dash 2 and Dash 3 components
 *
 * For more details, refer to the Dash documentation:
 * Dash 3 for Component Developers - https://dash.plotly.com/dash-3-for-component-developers
 */
import React, { useState, createElement } from "react";
import {dissoc, has, includes, isEmpty, isNil, mergeRight, type} from "ramda";

const SIMPLE_COMPONENT_TYPES = ['String', 'Number', 'Null', 'Boolean'];
const isSimpleComponent = component => includes(type(component), SIMPLE_COMPONENT_TYPES);


export const resolveChildProps = (child: any) => {
  if (child.props.componentPath) {
    // props are coming from Dash
    return (window as any).dash_component_api?.getLayout([
      ...child.props.componentPath,
      'props'
    ]);
  }
  // else props are coming from React (e.g. Demo.js, or Tabs.test.js)
  return child.props;
};

/** check for dash version */
export const isDash3 = (): boolean => {
    return !!(window as any).dash_component_api;
};


 // stringifies object ids used in pattern matching callbacks
export const stringifyId = (id: any): string => {
    if (isDash3) {
        return (window as any).dash_component_api.stringifyId(id)
    }

    if (typeof id !== 'object' || id === null) {
        return id;
    }

    const stringifyVal = (v: any) => (v && v.wild) || JSON.stringify(v);

    const parts = Object.keys(id)
        .sort()
        .map((key) => JSON.stringify(key) + ':' + stringifyVal(id[key]));

    return '{' + parts.join(',') + '}';
};


export const newRenderDashComponent = (component: any, index?: number | null, basePath?: any[]) => {
    if (!isDash3() || isEmpty(basePath) || !basePath) {
        const dash_extensions = require('dash-extensions-js');
        const {renderDashComponent} = dash_extensions;
        return renderDashComponent(component, index)
    }

    // Nothing to render.
    if (isNil(component) || isEmpty(component)) {
        return null;
    }

    // Simple stuff such as strings.
    if (isSimpleComponent(component)) {
        return component;
    }

    // Array of stuff.
    if (Array.isArray(component)) {
        return component.map((item, i) => newRenderDashComponent(item, i, [...(basePath || []), i, 'props']));
    }

    // Merge props.
    const allProps = {
        component,
        componentPath: [...(basePath || [])],
        key: index !== null ? index : Math.random().toString(36).substr(2, 9),
        temp: true
    };

    // Render the component.
    return createElement((window as any).dash_component_api.ExternalWrapper, allProps);
};