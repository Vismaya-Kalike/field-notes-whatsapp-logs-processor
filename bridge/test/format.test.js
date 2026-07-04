import { describe, it, expect } from 'vitest';
import { formatLines } from '../src/format.js';

const ts = new Date('2026-06-14T09:30:00');

describe('formatLines', () => {
  it('formats a plain text message', () => {
    const lines = formatLines({ ts, sender: 'Ravi Kumar', text: 'Attendance good' });
    expect(lines).toEqual(['14/06/26, 09:30 - Ravi Kumar: Attendance good']);
  });

  it('matches the python NEW_MSG_RE shape', () => {
    const [line] = formatLines({ ts, sender: 'Ravi Kumar', text: 'hi' });
    const re = /^(\d{2}\/\d{2}\/\d{2}), (\d{2}:\d{2}) - ([^:]+): ?(.*)$/;
    expect(re.test(line)).toBe(true);
  });

  it('emits attachment line then caption line', () => {
    const lines = formatLines({
      ts, sender: 'Ravi Kumar', text: 'great day',
      attachmentFilename: 'IMG-20260614-WA0001.jpg',
    });
    expect(lines).toEqual([
      '14/06/26, 09:30 - Ravi Kumar: IMG-20260614-WA0001.jpg (file attached)',
      'great day',
    ]);
  });

  it('emits only the attachment line when no caption', () => {
    const lines = formatLines({
      ts, sender: 'Ravi Kumar', text: '',
      attachmentFilename: 'IMG-20260614-WA0001.jpg',
    });
    expect(lines).toEqual([
      '14/06/26, 09:30 - Ravi Kumar: IMG-20260614-WA0001.jpg (file attached)',
    ]);
  });
});
