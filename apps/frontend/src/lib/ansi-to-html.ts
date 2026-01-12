/**
 * ANSI color code to HTML converter
 * Converts ANSI escape sequences to HTML spans with Tailwind CSS classes
 */

export interface AnsiToken {
  text: string;
  classes: string[];
}

/**
 * Parse ANSI escape sequences and convert to HTML-ready tokens
 */
export function ansiToHtml(text: string): AnsiToken[] {
  const tokens: AnsiToken[] = [];
  const ansiRegex = /\033\[([0-9;]+)m/g;
  let lastIndex = 0;
  let currentClasses: string[] = [];
  
  let match;
  while ((match = ansiRegex.exec(text)) !== null) {
    // Add text before the ANSI code
    if (match.index > lastIndex) {
      const textBefore = text.substring(lastIndex, match.index);
      if (textBefore) {
        tokens.push({ text: textBefore, classes: [...currentClasses] });
      }
    }
    
    // Parse ANSI code
    const codes = match[1].split(';').map(c => parseInt(c, 10));
    currentClasses = parseAnsiCodes(codes, currentClasses);
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining text
  if (lastIndex < text.length) {
    const remainingText = text.substring(lastIndex);
    if (remainingText) {
      tokens.push({ text: remainingText, classes: [...currentClasses] });
    }
  }
  
  // If no ANSI codes found, return original text
  if (tokens.length === 0) {
    tokens.push({ text, classes: [] });
  }
  
  return tokens;
}

/**
 * Parse ANSI color codes and return corresponding CSS classes
 */
function parseAnsiCodes(codes: number[], currentClasses: string[]): string[] {
  const classes: string[] = [];
  let bold = false;
  let fgColor: string | null = null;
  
  for (const code of codes) {
    if (code === 0) {
      // Reset
      return [];
    } else if (code === 1) {
      // Bold
      bold = true;
    } else if (code >= 30 && code <= 37) {
      // Foreground colors
      fgColor = getColorClass(code - 30, false);
    } else if (code === 39) {
      // Default foreground
      fgColor = null;
    } else if (code >= 90 && code <= 97) {
      // Bright foreground colors
      fgColor = getColorClass(code - 90, true);
    }
  }
  
  if (fgColor) {
    classes.push(fgColor);
  }
  if (bold) {
    classes.push('font-bold');
  }
  
  return classes;
}

/**
 * Map ANSI color codes to Tailwind CSS classes
 */
function getColorClass(colorIndex: number, bright: boolean): string {
  const colors = [
    'text-gray-400',      // Black (0) - use gray for visibility
    'text-red-400',      // Red (1)
    'text-green-400',    // Green (2)
    'text-yellow-400',   // Yellow (3)
    'text-blue-400',     // Blue (4)
    'text-magenta-400',  // Magenta (5)
    'text-cyan-400',     // Cyan (6)
    'text-gray-300',     // White (7)
  ];
  
  const brightColors = [
    'text-gray-300',     // Bright Black (0)
    'text-red-500',      // Bright Red (1)
    'text-green-500',    // Bright Green (2)
    'text-yellow-500',    // Bright Yellow (3)
    'text-blue-500',      // Bright Blue (4)
    'text-pink-500',     // Bright Magenta (5)
    'text-cyan-500',      // Bright Cyan (6)
    'text-white',         // Bright White (7)
  ];
  
  const palette = bright ? brightColors : colors;
  return palette[colorIndex] || 'text-gray-400';
}

/**
 * Convert ANSI text to HTML string
 */
export function ansiToHtmlString(text: string): string {
  const tokens = ansiToHtml(text);
  return tokens.map(token => {
    if (token.classes.length === 0) {
      return escapeHtml(token.text);
    }
    const classAttr = token.classes.join(' ');
    return `<span class="${classAttr}">${escapeHtml(token.text)}</span>`;
  }).join('');
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
