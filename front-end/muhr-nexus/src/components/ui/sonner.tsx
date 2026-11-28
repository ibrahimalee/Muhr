import { Toaster as Sonner, toast } from "sonner";

type ToasterProps = React.ComponentProps<typeof Sonner>;

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-sheet group-[.toaster]:text-ink group-[.toaster]:border-rule-strong group-[.toaster]:rounded-[4px] group-[.toaster]:shadow-[0_12px_30px_-12px_hsl(var(--ink)/0.35)] group-[.toaster]:font-sans",
          description: "group-[.toast]:text-graphite",
          actionButton: "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton: "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props}
    />
  );
};

export { Toaster, toast };
