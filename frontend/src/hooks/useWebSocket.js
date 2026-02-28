import { useState, useEffect, useRef, useCallback } from 'react';

export function useWebSocket(path) {
    const [messages, setMessages] = useState([]);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef(null);
    const reconnectRef = useRef(null);

    const connect = useCallback(() => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const url = `${protocol}//${host}${path}`;

        try {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                setIsConnected(true);
                if (reconnectRef.current) {
                    clearTimeout(reconnectRef.current);
                    reconnectRef.current = null;
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    setMessages(prev => [...prev, data]);
                } catch {
                    setMessages(prev => [...prev, { message: event.data }]);
                }
            };

            ws.onclose = () => {
                setIsConnected(false);
                // Auto-reconnect after 3 seconds
                reconnectRef.current = setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                ws.close();
            };
        } catch {
            reconnectRef.current = setTimeout(connect, 3000);
        }
    }, [path]);

    useEffect(() => {
        connect();
        return () => {
            if (wsRef.current) wsRef.current.close();
            if (reconnectRef.current) clearTimeout(reconnectRef.current);
        };
    }, [connect]);

    const clearMessages = useCallback(() => setMessages([]), []);

    return { messages, isConnected, clearMessages };
}
