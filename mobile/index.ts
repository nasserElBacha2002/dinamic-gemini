import { registerRootComponent } from 'expo';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import App from './App';

function Root(): JSX.Element {
  return React.createElement(SafeAreaProvider, null, React.createElement(App));
}

registerRootComponent(Root);
