import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConnectionState, WebSocketMessage } from '../types';

const WS_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/ws`;
const HEARTBEAT_INTERVAL = 30_000;
const MAX_RECONNECT_DELAY = 30_000;
const BASE_RECONNECT_DELAY = 1_000;

interface UseWebSocketOptions {
  onMessage?: (msg: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  autoConnect?: boolean;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { onMessage, onConnect, onDisconnect, autoConnect = true } = options;
  const [state, setState] = useState<ConnectionState>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval>>();
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const callbacksRef = useRef({ onMessage, onConnect, onDisconnect });

  callbacksRef.current = { onMessage, onConnect, onDisconnect };

  const cleanup = useCallback(() => {
    if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    cleanup();
    setState('connecting');

    const ws = new WebSocket(`${WS_URL}/alerts`);
    wsRef.current = ws;

    ws.onopen = () => {
      setState('connected');
      reconnectAttempts.current = 0;
      callbacksRef.current.onConnect?.();

      heartbeatTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, HEARTBEAT_INTERVAL);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        callbacksRef.current.onMessage?.(msg);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      // onclose will fire after onerror
    };

    ws.onclose = () => {
      setState('disconnected');
      callbacksRef.current.onDisconnect?.();
      if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);

      const delay = Math.min(
        BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts.current),
        MAX_RECONNECT_DELAY,
      );
      reconnectAttempts.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };
  }, [cleanup]);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    reconnectAttempts.current = Infinity; // prevent reconnect in onclose
    cleanup();
    setState('disconnected');
  }, [cleanup]);

  useEffect(() => {
    if (autoConnect) connect();
    return cleanup;
  }, [autoConnect, connect, cleanup]);

  return { state, connect, disconnect };
}
