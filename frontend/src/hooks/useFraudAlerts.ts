import { useCallback, useRef, useState } from 'react';
import type { FraudAlert, WebSocketMessage } from '../types';

const MAX_ALERTS = 100;

export function useFraudAlerts() {
  const [alerts, setAlerts] = useState<FraudAlert[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const buffer = useRef<FraudAlert[]>([]);

  const handleMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (msg.type !== 'alert') return;

      if (isPaused) {
        buffer.current.push(msg.data);
        if (buffer.current.length > MAX_ALERTS) {
          buffer.current = buffer.current.slice(-MAX_ALERTS);
        }
        return;
      }

      setAlerts((prev) => {
        const next = [msg.data, ...prev];
        return next.length > MAX_ALERTS ? next.slice(0, MAX_ALERTS) : next;
      });
    },
    [isPaused],
  );

  const pause = useCallback(() => setIsPaused(true), []);

  const resume = useCallback(() => {
    setAlerts((prev) => {
      const merged = [...buffer.current.reverse(), ...prev];
      buffer.current = [];
      return merged.length > MAX_ALERTS ? merged.slice(0, MAX_ALERTS) : merged;
    });
    setIsPaused(false);
  }, []);

  const clear = useCallback(() => {
    setAlerts([]);
    buffer.current = [];
  }, []);

  return {
    alerts,
    isPaused,
    bufferedCount: buffer.current.length,
    handleMessage,
    pause,
    resume,
    clear,
  };
}
