let setNum = $state('10497-1');

export const page = { get params() { return { set_num: setNum }; } };
export function setMockSetNum(value: string) { setNum = value; }
