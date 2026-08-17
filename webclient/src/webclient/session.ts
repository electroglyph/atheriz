import { ConnectionState } from './types';

export function shouldResetSession(wasConnected: boolean, nextState: ConnectionState): boolean {
    return wasConnected && (nextState === 'closed' || nextState === 'failed' || nextState === 'connecting');
}
