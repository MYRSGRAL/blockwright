#include <iostream>

using namespace std;

int main()
{
    double r;
    int n, x, y;
    int count = 0;

    cout << "Введите радиус круга (от 0 до 10000): ";
    cin >> r;

    if (cin.fail()) {
        cout << "Ошибка: радиус должен быть числом." << endl;
        return 1;
    }

    if (r < 0 || r > 10000) {
        cout << "Ошибка: радиус должен быть от 0 до 10000." << endl;
        return 1;
    }

    n = (int)r;
    for (x = -n; x <= n; x++) {
        for (y = -n; y <= n; y++) {
            if (x * x + y * y <= r * r) {
                count++;
            }
        }
    }

    cout << "Количество точек: " << count << endl;
    return 0;
}
