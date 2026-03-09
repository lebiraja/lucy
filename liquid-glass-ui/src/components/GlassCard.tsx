import { cn } from "@/lib/utils";
import { motion, type HTMLMotionProps } from "framer-motion";

interface GlassCardProps extends HTMLMotionProps<"div"> {
  glow?: boolean;
  children: React.ReactNode;
}

const GlassCard = ({ glow = false, className, children, ...props }: GlassCardProps) => (
  <motion.div
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, ease: "easeOut" }}
    className={cn(glow ? "glass-panel-glow" : "glass-panel", "p-5", className)}
    {...props}
  >
    {children}
  </motion.div>
);

export default GlassCard;
