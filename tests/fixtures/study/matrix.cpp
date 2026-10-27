#include <cctype>
#include <iostream>
#include <sstream>
#include <string>
#include <clocale>

using namespace std;

int main()
{
    setlocale(LC_ALL, "Russian");
    int a[20][20], b[20];
    int n, m, i, j;
    string line;
    istringstream input;
    char extra;

    cout << "Введите число строк и столбцов (от 1 до 20): ";
    getline(cin, line);
    input.str(line);
    if (!(input >> n) || (!input.eof() && !isspace(input.peek())) ||
        !(input >> m) || (input >> extra) ||
        n < 1 || n > 20 || m < 1 || m > 20) {
        cout << "Ошибка: нужны два размера от 1 до 20." << endl;
    return 1;
        }

        cout << "Введите матрицу: " << n << " строк по " << m
        << " целых чисел:" << endl;
        for (i = 0; i < n; i++) {
            line.clear();
            getline(cin, line);
            input.clear();
            input.str(line);
            for (j = 0; j < m; j++) {
                if (!(input >> a[i][j]) ||
                    (!input.eof() && !isspace(input.peek()))) {
                    cout << "Ошибка: строка должна содержать ровно " << m
                    << " целых чисел." << endl;
                return 1;
                    }
            }
            if (input >> extra) {
                cout << "Ошибка: строка должна содержать ровно " << m
                << " целых чисел." << endl;
                return 1;
            }
        }

        for (i = 0; i < n; i++) {
            b[i] = a[i][0];
            for (j = 1; j < m; j++) {
                if (a[i][j] > b[i]) {
                    b[i] = a[i][j];
                }
            }
        }

        cout << "Массив максимумов строк:";
        for (i = 0; i < n; i++) {
            cout << " " << b[i];
        }
        cout << endl;
        return 0;
}
