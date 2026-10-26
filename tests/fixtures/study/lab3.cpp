#include <iostream>

using namespace std;

int main()
{
    int a[100];
    int n, i, j;
    int count = 0;

    cout << "Введите количество элементов (от 1 до 100): ";
    cin >> n;
    if (cin.fail() || n < 1 || n > 100) {
        cout << "Ошибка: введите целое число от 1 до 100." << endl;
        return 1;
    }

    cout << "Введите " << n << " целых чисел: ";
    for (i = 0; i < n; i++) {
        cin >> a[i];
        if (cin.fail()) {
            cout << "Ошибка: элемент должен быть целым числом." << endl;
            return 1;
        }
    }

    for (i = 0; i < n - 1; i++) {
        for (j = i + 1; j < n; j++) {
            if (a[i] < a[j]) {
                count++;
            }
        }
    }

    cout << "Количество пар: " << count << endl;
    return 0;
}
