#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

using namespace std;

int main()
{
    double x;
    char extra;
    string line;

    cout << "Введите x: ";
    getline(cin, line);
    istringstream input(line);

    if (!(input >> x) || (input >> extra) || !isfinite(x)) {
        cout << "Ошибка: введите одно конечное число без лишних символов." << endl;
        return 1;
    }

    double power = 1.0;
    double sum = 1.0;
    int sign = -1;

    for (int i = 1; i <= 10; i++) {
        power = power * x;
        sum = sum + sign * (i + 1) * power / (i + 2);
        sign = -sign;
    }

    if (!isfinite(sum)) {
        cout << "Ошибка: результат не помещается в тип double." << endl;
        return 1;
    }

    cout << "x = " << x << endl;
    cout << fixed << setprecision(9);
    cout << "Сумма = " << sum << endl;
    return 0;
}
