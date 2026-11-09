// 실제 객석 좌표가 없을 때 관객·관리 화면에 같은 참고 배치를 사용한다.
function seatLayoutRows(seats, gradeOf) {
    const rowSize = 8;
    const rows = [];

    for (const grade of ["R", "S", ""]) {
        const group = seats.filter(seat => gradeOf(seat) === grade);
        for (let start = 0; start < group.length; start += rowSize) {
            const row = group.slice(start, start + rowSize);
            const offset = Math.floor((rowSize - row.length) / 2);
            rows.push({
                label: rows.length < 26 ? String.fromCharCode(65 + rows.length) : String(rows.length + 1),
                seats: row.map((seat, index) => {
                    const column = index + offset;
                    return { seat, column: column + (column < rowSize / 2 ? 2 : 3) };
                }),
            });
        }
    }
    return rows;
}
