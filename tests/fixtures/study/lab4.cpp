#include <iostream>
#include <sstream>
#include <string>

using namespace std;

int main()
{
    const int capacity = 100;
    int a[capacity];
    int n, limit, i;
    int k = 0;
    string line;
    char extra;

    cout << "Введите количество элементов (от 1 до 100): ";
    getline(cin, line);
    istringstream sizeInput(line);
    if (!cin || !(sizeInput >> n) || (sizeInput >> extra) || n < 1 || n > capacity) {
        cout << "Ошибка: введите целое число от 1 до 100." << endl;
        return 1;
    }

    cout << "Введите " << n << " целых чисел: ";
    getline(cin, line);
    istringstream arrayInput(line);
    i = 0;
    while (i < n && (arrayInput >> a[i])) {
        i++;
    }
    if (!cin || i != n || (arrayInput >> extra)) {
        cout << "Ошибка: введите ровно " << n << " целых чисел." << endl;
        return 1;
    }

    cout << "Введите заданное число: ";
    getline(cin, line);
    istringstream limitInput(line);
    if (!cin || !(limitInput >> limit) || (limitInput >> extra)) {
        cout << "Ошибка: заданное число должно быть целым." << endl;
        return 1;
    }

    for (i = 0; i < n; i++) {
        if (a[i] <= limit) {
            a[k] = a[i];
            k++;
        }
    }
    n = k;

    cout << "Количество оставшихся элементов: " << n << endl;
    cout << "Массив после удаления: ";
    if (n == 0) {
        cout << "пустой";
    } else {
        for (i = 0; i < n; i++) {
            cout << a[i] << ' ';
        }
    }
    cout << endl;
    return 0;
}
