<script lang="ts">
  import { cn } from '$lib/utils';
  import { X } from 'lucide-svelte';

  interface DialogProps {
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    closeOnEscape?: boolean;
  }

  let {
    open = $bindable(false),
    onOpenChange,
    children = $bindable(),
    closeOnEscape = true,
    ...rest
  }: DialogProps & { children?: import('svelte').Snippet } = $props();

  function handleClose() {
    open = false;
    onOpenChange?.(false);
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-center justify-center"
    role="presentation"
  >
    <button 
      class="fixed inset-0 bg-black/50 border-none p-0 cursor-pointer"
      type="button"
      aria-label="Close dialog"
      onclick={handleClose}
    ></button>
    <div
      class={cn(
        'relative z-50 w-full max-w-lg bg-background p-6 shadow-lg rounded-lg',
        rest.class
      )}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      onkeydown={(e) => e.key === 'Escape' && closeOnEscape && handleClose()}
      onmousedown={(e) => e.stopPropagation()}
      ontouchstart={(e) => e.stopPropagation()}
    >
      <button
        onclick={handleClose}
        class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
      >
        <X class="h-4 w-4" />
        <span class="sr-only">Close</span>
      </button>
      {#if children}{@render children()}{/if}
    </div>
  </div>
{/if}
