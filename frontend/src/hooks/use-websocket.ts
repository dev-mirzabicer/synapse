"use client";

import { useState, useEffect, useRef } from 'react';
import { WS_BASE_URL, JWT_TOKEN_KEY } from '@/lib/constants';
import type { MessageHistoryRead } from '@/types';

export function useWebSocket(groupId: string | null) {
  const [lastMessage, setLastMessage] = useState<MessageHistoryRead | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Event | null>(null);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!groupId) {
      return;
    }
    
    const token = localStorage.getItem(JWT_TOKEN_KEY);
    if (!token) {
        console.error("No token found for WebSocket connection");
        return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = WS_BASE_URL.replace(/^https?:/, protocol) + `/ws/${groupId}?token=${token}`;
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    ws.current.onmessage = (event) => {
      try {
        const messageData = JSON.parse(event.data);
        setLastMessage(messageData);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.current.onerror = (event) => {
      console.error('WebSocket error:', event);
      setError(event);
      setIsConnected(false);
    };

    ws.current.onclose = () => {
      setIsConnected(false);
    };

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [groupId]);

  return { lastMessage, isConnected, error };
}
