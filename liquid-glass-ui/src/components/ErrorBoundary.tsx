import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary — wraps route children to prevent blank pages on render errors.
 * Displays a friendly error card instead of a white screen.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, info);
  }

  reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex h-[60vh] items-center justify-center">
          <div className="glass-panel max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3">
              <span className="status-dot-offline" />
              <h2 className="text-sm font-medium text-foreground">Something went wrong</h2>
            </div>
            <p className="text-xs text-muted-foreground font-mono break-words">
              {this.state.error?.message ?? "Unknown error"}
            </p>
            <button
              onClick={this.reset}
              className="glass-button text-xs text-primary border-primary/20 hover:border-primary/40"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
