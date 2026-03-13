import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Consumes a Server-Sent Events endpoint.
 * Automatically closes when the server sends { type: "done" }.
 *
 * @param {string|null} url  Full path, e.g. "/api/tasks/42/events". Pass null to not connect.
 * @returns {{ events: object[], isDone: boolean, isStreaming: boolean, clear: function }}
 */
export function useSSE(url) {
    const [events, setEvents] = useState([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [isDone, setIsDone] = useState(false);
    const esRef = useRef(null);

    const clear = useCallback(() => {
        setEvents([]);
        setIsDone(false);
        setIsStreaming(false);
    }, []);

    useEffect(() => {
        if (!url) return;

        // Close any previous connection
        if (esRef.current) {
            esRef.current.close();
            esRef.current = null;
        }

        setEvents([]);
        setIsDone(false);
        setIsStreaming(true);

        const es = new EventSource(url);
        esRef.current = es;

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'done') {
                    setIsDone(true);
                    setIsStreaming(false);
                    es.close();
                    esRef.current = null;
                } else {
                    setEvents(prev => {
                        const next = [...prev, data];
                        return next.length > 500 ? next.slice(-500) : next;
                    });
                }
            } catch {
                // ignore parse errors
            }
        };

        es.onerror = () => {
            setIsStreaming(false);
            es.close();
            esRef.current = null;
        };

        return () => {
            es.close();
            esRef.current = null;
        };
    }, [url]);

    return { events, isDone, isStreaming, clear };
}
