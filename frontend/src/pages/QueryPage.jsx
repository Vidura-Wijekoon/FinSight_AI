import { useCallback, useEffect, useRef, useState } from 'react';
import { ragQuery } from '../api/client';

// Unique ID for messages
let _id = 0;
const uid = () => ++_id;

export default function QueryPage() {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [topK, setTopK] = useState(4);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const messagesEndRef = useRef(null);

    // Scroll to the latest message
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, loading]);

    const handleSend = useCallback(async () => {
        const q = input.trim();
        if (!q || loading) return;
        if (q.length < 3) {
            setError('Query must be at least 3 characters.');
            return;
        }
        setError('');
        setInput('');
        const userMsg = { id: uid(), role: 'user', content: q };
        setMessages(prev => [...prev, userMsg]);
        setLoading(true);
        try {
            const data = await ragQuery(q, topK);
            const assistantMsg = {
                id: uid(),
                role: 'assistant',
                content: data.answer,
                citations: data.citations?.filter(c => c.cited_in_answer) ?? [],
                meta: {
                    latency_ms: data.latency_ms,
                    chunks_used: data.chunks_used,
                    model_used: data.model_used,
                },
            };
            setMessages(prev => [...prev, assistantMsg]);
        } catch (err) {
            const errMsg = {
                id: uid(),
                role: 'assistant',
                content: `❌ Query failed: ${err.message}`,
                isError: true,
            };
            setMessages(prev => [...prev, errMsg]);
        } finally {
            setLoading(false);
        }
    }, [input, topK, loading]);

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const clearHistory = () => setMessages([]);

    return (
        <>
            <div className="page-header" style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div>
                        <h1 className="page-title">💬 Financial Query</h1>
                        <p className="page-subtitle">Ask questions about your indexed financial documents.</p>
                    </div>
                    {messages.length > 0 && (
                        <button className="btn btn-ghost btn-sm" onClick={clearHistory}>
                            🗑️ Clear
                        </button>
                    )}
                </div>
            </div>

            {error && <div className="alert alert-error mb-4">⚠️ {error}</div>}

            {/* Chat container */}
            <div className="chat-container">
                {/* Messages */}
                <div className="chat-messages" id="chat-messages">
                    {messages.length === 0 && !loading && (
                        <div className="chat-empty">
                            <div className="chat-empty-icon">🔍</div>
                            <p>Ask a question about your financial documents to get started.</p>
                            <p style={{ fontSize: '0.8rem' }}>
                                Powered by llama3.1:8b (local inference) · all-MiniLM-L6-v2 embeddings
                            </p>
                        </div>
                    )}

                    {messages.map((msg) => (
                        <div key={msg.id} className={`message ${msg.role}`}>
                            <div className="message-avatar">
                                {msg.role === 'user' ? '👤' : '📊'}
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div className={`message-bubble${msg.isError ? ' alert-error' : ''}`}>
                                    {msg.content}
                                </div>

                                {/* Citations */}
                                {msg.citations?.length > 0 && (
                                    <div className="citations-section">
                                        <span className="citations-label">📎 Sources:</span>
                                        {msg.citations.map((c, i) => (
                                            <span key={i} className="citation-badge">
                                                [Chunk {c.chunk_num}] {c.source_file} — {c.relevance_score.toFixed(2)}
                                            </span>
                                        ))}
                                    </div>
                                )}

                                {/* Meta */}
                                {msg.meta && (
                                    <div className="message-meta">
                                        <span className="meta-item">🕐 {msg.meta.latency_ms.toFixed(0)} ms</span>
                                        <span className="meta-item">🧩 {msg.meta.chunks_used} chunks</span>
                                        <span className="meta-item">🤖 {msg.meta.model_used}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}

                    {/* Loading indicator */}
                    {loading && (
                        <div className="message assistant">
                            <div className="message-avatar">📊</div>
                            <div className="message-bubble" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <div className="spinner" />
                                <span style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                                    Retrieving context and generating answer…
                                </span>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input area */}
                <div className="chat-input-area">
                    <textarea
                        id="query-input"
                        className="chat-input"
                        placeholder="Ask a question about your financial documents… (Enter to send, Shift+Enter for newline)"
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={loading}
                        rows={1}
                    />

                    <div className="topk-control">
                        <span className="topk-label">Top-K</span>
                        <input
                            id="topk-input"
                            type="number"
                            className="form-input topk-input"
                            min={1}
                            max={20}
                            value={topK}
                            onChange={e => setTopK(Number(e.target.value))}
                            disabled={loading}
                        />
                    </div>

                    <button
                        id="send-query-btn"
                        className="btn btn-primary"
                        onClick={handleSend}
                        disabled={!input.trim() || loading}
                        title="Send query (Enter)"
                    >
                        {loading ? <div className="spinner" /> : '➤'}
                    </button>
                </div>
            </div>
        </>
    );
}
