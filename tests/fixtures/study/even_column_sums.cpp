#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <iostream>

using namespace std;

int main()
{
    int a[100][100];
    int n, m, mode;
    int count = 0;
    long long sum;

    cout << "Введите число строк и столбцов (1-100): ";
    if (!(cin >> n >> m) || n < 1 || n > 100 || m < 1 || m > 100) {
        cout << "Ошибка: размеры должны быть целыми числами от 1 до 100." << endl;
        return 1;
    }
    cout << "Заполнение: 1 - вручную, 2 - случайно (-10..10): ";
    if (!(cin >> mode) || (mode != 1 && mode != 2)) {
        cout << "Ошибка: выберите 1 или 2." << endl;
        return 1;
    }

    if (mode == 2) {
        srand(time(nullptr));
    } else {
        cout << "Введите элементы матрицы по строкам:" << endl;
    }
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            if (mode == 1) {
                if (!(cin >> a[i][j])) {
                    cout << "Ошибка: элементы должны быть целыми числами." << endl;
                    return 1;
                }
            } else {
                a[i][j] = rand() % 21 - 10;
            }
        }
    }

    cout << "Матрица:" << endl;
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < m; j++) {
            cout << setw(12) << a[i][j];
        }
        cout << endl;
    }

    for (int j = 0; j < m; j++) {
        sum = 0;
        for (int i = 0; i < n; i++) {
            sum = sum + a[i][j];
        }
        if (sum % 2 == 0) {
            count++;
        }
    }
    cout << "Количество столбцов с чётной суммой: " << count << endl;
    return 0;
}
