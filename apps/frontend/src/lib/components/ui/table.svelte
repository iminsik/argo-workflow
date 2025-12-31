<script lang="ts">
  import { cn } from '$lib/utils';
  import type { HTMLAttributes } from 'svelte/elements';

  interface TableProps extends HTMLAttributes<HTMLTableElement> {}
  interface TableHeaderProps extends HTMLAttributes<HTMLTableSectionElement> {}
  interface TableBodyProps extends HTMLAttributes<HTMLTableSectionElement> {}
  interface TableRowProps extends HTMLAttributes<HTMLTableRowElement> {}
  interface TableHeadProps extends HTMLAttributes<HTMLTableCellElement> {}
  interface TableCellProps extends HTMLAttributes<HTMLTableCellElement> {}

  export let class: string = $bindable('');
</script>

<!-- Table -->
<table class={cn('w-full caption-bottom text-sm', class)}>
  {@render rest.children?.()}
</table>

<!-- Table Header -->
<svelte:fragment slot="header">
  <thead class={cn('[&_tr]:border-b', class)}>
    {@render rest.children?.()}
  </thead>
</svelte:fragment>

<!-- Table Body -->
<svelte:fragment slot="body">
  <tbody class={cn('[&_tr:last-child]:border-0', class)}>
    {@render rest.children?.()}
  </tbody>
</svelte:fragment>

<!-- Table Row -->
<tr class={cn('border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted', class)}>
  {@render rest.children?.()}
</tr>

<!-- Table Head -->
<th class={cn('h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0', class)}>
  {@render rest.children?.()}
</th>

<!-- Table Cell -->
<td class={cn('p-4 align-middle [&:has([role=checkbox])]:pr-0', class)}>
  {@render rest.children?.()}
</td>

