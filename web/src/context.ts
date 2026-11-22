import { createContext, useContext } from 'react';
import type { ReaderHost } from './types';

export const HostContext = createContext<ReaderHost | null>(null);
export const useHost = () => useContext(HostContext);
